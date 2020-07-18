import json
import logging
import os
from tempfile import NamedTemporaryFile
from wsgiref.util import FileWrapper

from django.conf import settings
from django.core.files import File as DjFile
from django.core.files.storage import default_storage
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from le_utils.constants import content_kinds
from le_utils.constants import exercises
from le_utils.constants import file_formats
from le_utils.constants import format_presets
from le_utils.constants.languages import getlang_by_alpha2
from pressurecooker.subtitles import build_subtitle_converter
from pressurecooker.subtitles import InvalidSubtitleFormatError
from pressurecooker.subtitles import LANGUAGE_CODE_UNKNOWN
from pressurecooker.videos import guess_video_preset_by_resolution
from rest_framework.authentication import SessionAuthentication
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import authentication_classes
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer

from contentcuration.api import get_hash
from contentcuration.api import write_file_to_storage
from contentcuration.models import ContentNode
from contentcuration.models import File
from contentcuration.models import FormatPreset
from contentcuration.models import generate_object_storage_name
from contentcuration.models import generate_storage_url
from contentcuration.models import License
from contentcuration.serializers import ContentNodeEditSerializer
from contentcuration.serializers import FileSerializer
from contentcuration.utils.files import generate_thumbnail_from_node
from contentcuration.utils.files import get_thumbnail_encoding


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def file_upload(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    # Implement logic for switching out files without saving it yet
    filename, ext = os.path.splitext(request.FILES.values()[0]._name)
    size = request.FILES.values()[0]._size
    contentfile = DjFile(request.FILES.values()[0])
    checksum = get_hash(contentfile)
    request.user.check_space(size, checksum)

    file_object = File(
        file_size=size,
        file_on_disk=contentfile,
        checksum=checksum,
        file_format_id=ext[1:].lower(),
        original_filename=request.FILES.values()[0]._name,
        preset_id=request.META.get('HTTP_PRESET'),
        language_id=request.META.get('HTTP_LANGUAGE'),
        uploaded_by=request.user,
    )
    file_object.save()

    return HttpResponse(json.dumps({
        "success": True,
        "filename": str(file_object),
        "file": JSONRenderer().render(FileSerializer(file_object).data)
    }))


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def file_create(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    original_filename, ext = os.path.splitext(request.FILES.values()[0]._name)
    size = request.FILES.values()[0]._size
    contentfile = DjFile(request.FILES.values()[0])
    checksum = get_hash(contentfile)
    request.user.check_space(size, checksum)

    presets = FormatPreset.objects.filter(allowed_formats__extension__contains=ext[1:].lower())
    kind = presets.first().kind
    preferences = json.loads(request.POST.get('content_defaults', None) or "{}")

    license = License.objects.filter(license_name=preferences.get('license')).first()  # Use filter/first in case preference hasn't been set
    license_id = license.pk if license else None
    new_node = ContentNode(
        title=original_filename,
        kind=kind,
        license_id=license_id,
        author=preferences.get('author') or "",
        aggregator=preferences.get('aggregator') or "",
        provider=preferences.get('provider') or "",
        copyright_holder=preferences.get('copyright_holder'),
        parent_id=settings.ORPHANAGE_ROOT_ID,
    )
    if license and license.is_custom:
        new_node.license_description = preferences.get('license_description')
    # The orphanage is not an actual tree but just a long list of items.
    with ContentNode.objects.disable_mptt_updates():
        new_node.save()
    file_object = File(
        file_on_disk=contentfile,
        checksum=checksum,
        file_format_id=ext[1:].lower(),
        original_filename=request.FILES.values()[0]._name,
        contentnode=new_node,
        file_size=size,
        uploaded_by=request.user,
    )
    file_object.save()

    if kind.pk == content_kinds.VIDEO:
        file_object.preset_id = guess_video_preset_by_resolution(str(file_object.file_on_disk))
    elif presets.filter(supplementary=False).count() == 1:
        file_object.preset = presets.filter(supplementary=False).first()
    file_object.save()

    thumbnail = None
    try:
        if preferences.get('auto_derive_video_thumbnail') and new_node.kind_id == content_kinds.VIDEO \
                or preferences.get('auto_derive_audio_thumbnail') and new_node.kind_id == content_kinds.AUDIO \
                or preferences.get('auto_derive_html5_thumbnail') and new_node.kind_id == content_kinds.HTML5 \
                or preferences.get('auto_derive_document_thumbnail') and new_node.kind_id == content_kinds.DOCUMENT:
            thumbnail = generate_thumbnail_from_node(new_node, set_node=True)
            request.user.check_space(thumbnail.file_size, thumbnail.checksum)
    except Exception:
        if thumbnail:
            thumbnail.delete()

    return HttpResponse(json.dumps({
        "success": True,
        "node": JSONRenderer().render(ContentNodeEditSerializer(new_node).data)
    }))


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def generate_thumbnail(request, contentnode_id):
    logging.debug("Entering the generate_thumbnail endpoint")

    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    node = ContentNode.objects.get(pk=contentnode_id)

    thumbnail_object = generate_thumbnail_from_node(node)

    try:
        request.user.check_space(thumbnail_object.file_size, thumbnail_object.checksum)
    except Exception as e:
        if thumbnail_object:
            thumbnail_object.delete()
        raise e

    return HttpResponse(json.dumps({
        "success": True,
        "file": JSONRenderer().render(FileSerializer(thumbnail_object).data),
        "path": generate_storage_url(str(thumbnail_object)),
        "encoding": get_thumbnail_encoding(str(thumbnail_object)),
    }))


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def thumbnail_upload(request):
    # Used for channels
    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    fobj = request.FILES.values()[0]
    checksum = get_hash(DjFile(fobj))
    request.user.check_space(fobj._size, checksum)

    formatted_filename = write_file_to_storage(fobj)

    return HttpResponse(json.dumps({
        "success": True,
        "formatted_filename": formatted_filename,
        "file": None,
        "path": generate_storage_url(formatted_filename),
        "encoding": get_thumbnail_encoding(formatted_filename),
    }))


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def image_upload(request):
    # Used for content nodes
    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    fobj = request.FILES.values()[0]
    name, ext = os.path.splitext(fobj._name)  # gets file extension without leading period
    checksum = get_hash(DjFile(fobj))
    request.user.check_space(fobj._size, checksum)

    file_object = File(
        contentnode_id=request.META.get('HTTP_NODE'),
        original_filename=name,
        preset_id=request.META.get('HTTP_PRESET'),
        file_on_disk=DjFile(request.FILES.values()[0]),
        file_format_id=ext[1:].lower(),
        uploaded_by=request.user
    )
    file_object.save()
    return HttpResponse(json.dumps({
        "success": True,
        "file": JSONRenderer().render(FileSerializer(file_object).data),
        "path": generate_storage_url(str(file_object)),
        "encoding": get_thumbnail_encoding(str(file_object)),
    }))


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def exercise_image_upload(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    fobj = request.FILES.values()[0]
    assessment_item_id = request.POST.get('assessment_item_id', None)
    name, ext = os.path.splitext(fobj._name)
    get_hash(DjFile(fobj))
    file_object = File(
        preset_id=format_presets.EXERCISE_IMAGE,
        file_on_disk=DjFile(request.FILES.values()[0]),
        file_format_id=ext[1:].lower(),
        assessment_item_id=assessment_item_id,
    )
    file_object.save()
    return HttpResponse(json.dumps({
        "success": True,
        "formatted_filename": exercises.CONTENT_STORAGE_FORMAT.format(str(file_object)),
        "file_id": file_object.pk,
        "path": generate_storage_url(str(file_object)),
    }))


def subtitle_upload(request):
    # File will be converted to VTT format
    ext = file_formats.VTT
    language_id = request.META.get('HTTP_LANGUAGE')
    content_file = request.FILES.values()[0]

    with NamedTemporaryFile() as temp_file:
        try:
            converter = build_subtitle_converter(unicode(content_file.read(), 'utf-8'))
            convert_language_code = language_id

            # We're making the assumption here that language the user selected is truly the caption
            # file's language if it's unknown
            if len(converter.get_language_codes()) == 1 \
                    and converter.has_language(LANGUAGE_CODE_UNKNOWN):
                converter.replace_unknown_language(language_id)

            # determine if the request language exists by another code, otherwise we can't continue
            if not converter.has_language(convert_language_code):
                for language_code in converter.get_language_codes():
                    language = getlang_by_alpha2(language_code)
                    if language and language.code == language_id:
                        convert_language_code = language_code
                        break
                else:
                    return HttpResponseBadRequest(
                        "Language '{}' not present in subtitle file".format(language_id))

            converter.write(temp_file.name, convert_language_code)
        except InvalidSubtitleFormatError as ex:
            return HttpResponseBadRequest("Subtitle conversion failed: {}".format(ex))

        temp_file.seek(0)
        converted_file = DjFile(temp_file)

        checksum = get_hash(converted_file)
        size = converted_file.size
        request.user.check_space(size, checksum)

        file_object = File(
            file_size=size,
            file_on_disk=converted_file,
            checksum=checksum,
            file_format_id=ext,
            original_filename=request.FILES.values()[0]._name,
            preset_id=request.META.get('HTTP_PRESET'),
            language_id=language_id,
            uploaded_by=request.user,
        )
        file_object.save()

    return HttpResponse(json.dumps({
        "success": True,
        "filename": str(file_object),
        "file": JSONRenderer().render(FileSerializer(file_object).data)
    }))


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def multilanguage_file_upload(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    if not request.META.get('HTTP_LANGUAGE'):
        return HttpResponseBadRequest("Language is required")

    preset_id = request.META.get('HTTP_PRESET')
    if preset_id == format_presets.VIDEO_SUBTITLE:
        return subtitle_upload(request)
    else:
        return HttpResponseBadRequest("Unsupported preset" if preset_id else "Preset is required")


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def debug_serve_file(request, path):
    # There's a problem with loading exercise images, so use this endpoint
    # to serve the image files to the /content/storage url
    filename = os.path.basename(path)
    checksum, _ext = os.path.splitext(filename)
    filepath = generate_object_storage_name(checksum, filename)

    if not default_storage.exists(filepath):
        raise Http404("The object requested does not exist.")
    with default_storage.open(filepath, 'rb') as fobj:
        response = HttpResponse(FileWrapper(fobj), content_type="application/octet-stream")
        return response


def debug_serve_content_database_file(request, path):
    filename = os.path.basename(path)
    path = "/".join([settings.DB_ROOT, filename])
    if not default_storage.exists(path):
        raise Http404("The object requested does not exist.")
    with default_storage.open(path, "rb") as f:
        response = HttpResponse(FileWrapper(f), content_type="application/octet-stream")
        return response
