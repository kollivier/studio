import copy
import re

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import ObjectDoesNotExist
from django_filters.rest_framework import DjangoFilterBackend
from django_s3_storage.storage import S3Error
from le_utils.constants import exercises
from le_utils.constants import format_presets
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import ValidationError

from contentcuration.models import AssessmentItem
from contentcuration.models import ContentNode
from contentcuration.models import File
from contentcuration.models import generate_object_storage_name
from contentcuration.viewsets.base import BulkListSerializer
from contentcuration.viewsets.base import BulkModelSerializer
from contentcuration.viewsets.base import ValuesViewset
from contentcuration.viewsets.base import RequiredFilterSet
from contentcuration.viewsets.common import NotNullArrayAgg
from contentcuration.viewsets.common import UUIDInFilter
from contentcuration.viewsets.sync.constants import ASSESSMENTITEM
from contentcuration.viewsets.sync.constants import CREATED
from contentcuration.viewsets.sync.constants import DELETED


exercise_image_filename_regex = re.compile(
    r"\!\[[^]]*\]\(\${placeholder}/([a-f0-9]{{32}}\.[0-9a-z]+)\)".format(
        placeholder=exercises.IMG_PLACEHOLDER
    )
)


class AssessmentItemFilter(RequiredFilterSet):
    id__in = UUIDInFilter(field_name="id")
    contentnode__in = UUIDInFilter(field_name="contentnode")

    class Meta:
        model = AssessmentItem
        fields = (
            "id",
            "id__in",
            "contentnode",
            "contentnode__in",
        )


def get_filenames_from_assessment(assessment_item):
    # Get unique checksums in the assessment item text fields markdown
    # Coerce to a string, for Python 2, as the stored data is in unicode, and otherwise
    # the unicode char in the placeholder will not match
    return set(
        exercise_image_filename_regex.findall(
            str(
                assessment_item.question
                + assessment_item.answers
                + assessment_item.hints
            )
        )
    )


class AssessmentListSerializer(BulkListSerializer):
    def set_files(self, all_objects):
        all_filenames = [get_filenames_from_assessment(obj) for obj in all_objects]
        files_to_delete = File.objects.none()
        files_to_create = []
        for aitem, filenames in zip(all_objects, all_filenames):
            checksums = [filename.split(".")[0] for filename in filenames]
            files_to_delete |= aitem.files.exclude(checksum__in=checksums)
            no_files = [
                filename
                for filename in filenames
                if filename.split(".")[0]
                in (checksums - set(aitem.files.values_list("checksum", flat=True)))
            ]
            for filename in no_files:
                checksum = filename.split(".")[0]
                file_path = generate_object_storage_name(checksum, filename)
                try:
                    file_object = default_storage.open(file_path)
                    # Only do this if the file already exists, otherwise, hope it comes into being later!
                    files_to_create.append(
                        File(
                            assessment_item=aitem,
                            checksum=checksum,
                            file_on_disk=file_object,
                            preset_id=format_presets.EXERCISE_IMAGE,
                        )
                    )
                except S3Error:
                    # File does not exist yet not much we can do about that here.
                    pass
        files_to_delete.delete()
        File.objects.bulk_create(files_to_create)

    def create(self, validated_data):
        all_objects = super(AssessmentListSerializer, self).create(validated_data)
        self.set_files(all_objects)
        return all_objects

    def update(self, queryset, all_validated_data):
        all_objects = super(AssessmentListSerializer, self).update(
            queryset, all_validated_data
        )
        self.set_files(all_objects)
        return all_objects


class AssessmentItemSerializer(BulkModelSerializer):
    class Meta:
        model = AssessmentItem
        fields = (
            "id",
            "question",
            "type",
            "answers",
            "contentnode",
            "assessment_id",
            "hints",
            "raw_data",
            "order",
            "source_url",
            "randomize",
            "deleted",
        )
        list_serializer_class = AssessmentListSerializer
        # Use the assessment_id as the lookup field for updates
        # this may cause poor performance on updates as this field is not
        # indexed. Monitor and potentially add an index.
        update_lookup_field = "assessment_id"


class AssessmentItemViewSet(ValuesViewset):
    queryset = AssessmentItem.objects.all()
    serializer_class = AssessmentItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (DjangoFilterBackend,)
    filter_class = AssessmentItemFilter
    values = (
        "id",
        "question",
        "type",
        "answers",
        "contentnode_id",
        "assessment_id",
        "hints",
        "raw_data",
        "order",
        "source_url",
        "randomize",
        "deleted",
    )

    field_map = {
        "contentnode": "contentnode_id",
    }

    def annotate_queryset(self, queryset):
        queryset = queryset.annotate(file_ids=NotNullArrayAgg("files__id"))
        return queryset

    def copy(self, pk, user=None, from_key=None, **mods):
        try:
            item = AssessmentItem.objects.get(assessment_id=from_key)
        except AssessmentItem.DoesNotExist:
            error = ValidationError("Copy assessment item source does not exist")
            return str(error), None

        if AssessmentItem.objects.filter(assessment_id=pk).exists():
            error = ValidationError("Copy pk already exists")
            return str(error), None

        try:
            contentnode_id = mods.pop("contentnode", None)

            if not contentnode_id:
                raise ValidationError("Field `contentnode` is required")

            contentnode = ContentNode.objects.get(pk=contentnode_id)

            with transaction.atomic():
                new_item = copy.copy(item)
                new_item.assessment_id = pk
                new_item.contentnode = contentnode
                new_item.save()

        except (ObjectDoesNotExist, ValidationError) as e:
            e = e if isinstance(e, ValidationError) else ValidationError(e)

            # if contentnode doesn't exist
            return str(e), [dict(key=pk, table=ASSESSMENTITEM, type=DELETED,)]

        return (
            None,
            [
                dict(
                    key=pk,
                    table=ASSESSMENTITEM,
                    type=CREATED,
                    obj=AssessmentItemSerializer(instance=new_item),
                )
            ],
        )
