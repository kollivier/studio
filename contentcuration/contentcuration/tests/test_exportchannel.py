from __future__ import absolute_import

import base64
import os
import random
import string
import tempfile

import pytest
from django.db import connections
from kolibri_content import models
from kolibri_content.router import set_active_content_database
from mock import patch

from .base import StudioTestCase
from .testdata import create_studio_file
from .testdata import exercise
from .testdata import fileobj_video
from .testdata import slideshow
from .testdata import topic
from .testdata import video
from contentcuration import models as cc
from contentcuration.tests.utils import mixer
from contentcuration.utils.publish import convert_channel_thumbnail
from contentcuration.utils.publish import create_bare_contentnode
from contentcuration.utils.publish import create_content_database
from contentcuration.utils.publish import create_slideshow_manifest
from contentcuration.utils.publish import fill_published_fields
from contentcuration.utils.publish import map_prerequisites
from contentcuration.utils.publish import MIN_SCHEMA_VERSION
from contentcuration.utils.publish import prepare_export_database
from contentcuration.utils.publish import set_channel_icon_encoding

pytestmark = pytest.mark.django_db


def thumbnail():
    image_data = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
    file_data = create_studio_file(base64.decodebytes(image_data), preset='channel_thumbnail', ext='png')
    return file_data['name']


def assessment_item():
    answers = "[{\"correct\": false, \"answer\": \"White Rice\", \"help_text\": \"\"}, " \
              "{\"correct\": true, \"answer\": \"Brown Rice\", \"help_text\": \"\"}, " \
              "{\"correct\": false, \"answer\": \"Rice Krispies\", \"help_text\": \"\"}]"
    return mixer.blend(cc.AssessmentItem, question='Which rice is the healthiest?',
                       type='single_selection', answers=answers)


def assessment_item2():
    answers = "[{\"correct\": true, \"answer\": \"Eggs\", \"help_text\": \"\"}, " \
              "{\"correct\": true, \"answer\": \"Tofu\", \"help_text\": \"\"}, " \
              "{\"correct\": true, \"answer\": \"Meat\", \"help_text\": \"\"}, " \
              "{\"correct\": true, \"answer\": \"Beans\", \"help_text\": \"\"}, " \
              "{\"correct\": false, \"answer\": \"Rice\", \"help_text\": \"\"}]"
    return mixer.blend(cc.AssessmentItem, question='Which of the following are proteins?',
                       type='multiple_selection', answers=answers)


def assessment_item3():
    answers = "[]"
    return mixer.blend(cc.AssessmentItem, question='Why a rice cooker?', type='free_response', answers=answers)


def assessment_item4():
    answers = "[{\"correct\": true, \"answer\": 20, \"help_text\": \"\"}]"
    return mixer.blend(cc.AssessmentItem, question='How many minutes does it take to cook rice?',
                       type='input_question', answers=answers)


def description():
    return "".join(random.sample(string.printable, 20))


def channel():
    with cc.ContentNode.objects.delay_mptt_updates():
        # Note: we used to use mixer.blend when creating these objects, but after upgrading to Django 2,
        # the blended objects had invalid mptt tree data, which stopped occurring once we started creating
        # objects purely using the Django ORM.
        root = cc.ContentNode.objects.create(title="root", parent=None, kind=topic())
        level1 = cc.ContentNode.objects.create(parent=root, kind=topic())
        level2 = cc.ContentNode(parent=level1, kind=topic())
        leaf = cc.ContentNode.objects.create(parent=level1, kind=video())
        leaf2 = cc.ContentNode.objects.create(parent=level1, kind=exercise(), title='EXERCISE 1', extra_fields={
            'mastery_model': 'do_all',
           'randomize': True
        })
        # FIXME: Uncommenting the below line on Django 2.0+ gives an error with our custom mptt manager handling.
        # cc.ContentNode.objects.create(parent=level2, kind=slideshow(), title="SLIDESHOW 1", extra_fields={})

        video_file = fileobj_video()
        video_file.contentnode = leaf
        video_file.save()

        item = assessment_item()
        item.contentnode = leaf2
        item.save()

        item2 = assessment_item()
        item2.contentnode = leaf2
        item2.save()

        item3 = assessment_item()
        item3.contentnode = leaf2
        item3.save()

        item4 = assessment_item()
        item4.contentnode = leaf2
        item4.save()

    channel = cc.Channel.objects.create(main_tree=root, name='testchannel', thumbnail=thumbnail())

    return channel


class ExportChannelTestCase(StudioTestCase):

    @classmethod
    def setUpClass(cls):
        super(ExportChannelTestCase, cls).setUpClass()
        cls.patch_copy_db = patch('contentcuration.utils.publish.save_export_database')
        cls.patch_copy_db.start()

    @classmethod
    def tearDownClass(cls):
        super(ExportChannelTestCase, cls).tearDownClass()
        cls.patch_copy_db.stop()

    def setUp(self):
        super(ExportChannelTestCase, self).setUp()
        self.content_channel = channel()
        set_channel_icon_encoding(self.content_channel)
        self.tempdb = create_content_database(self.content_channel, True, None, True)

        set_active_content_database(self.tempdb)

    def tearDown(self):
        super(ExportChannelTestCase, self).tearDown()
        set_active_content_database(None)
        if os.path.exists(self.tempdb):
            os.remove(self.tempdb)

    def test_channel_rootnode_data(self):
        channel = models.ChannelMetadata.objects.first()
        self.assertEqual(channel.root_pk, channel.root_id)

    def test_channel_version_data(self):
        channel = models.ChannelMetadata.objects.first()
        self.assertEqual(channel.min_schema_version, MIN_SCHEMA_VERSION)

    def test_contentnode_license_data(self):
        for node in models.ContentNode.objects.all():
            if node.license:
                self.assertEqual(node.license_name, node.license.license_name)
                self.assertEqual(node.license_description, node.license.license_description)

    def test_contentnode_channel_id_data(self):
        channel = models.ChannelMetadata.objects.first()
        for node in models.ContentNode.objects.all():
            self.assertEqual(node.channel_id, channel.id)

    def test_contentnode_file_checksum_data(self):
        for file in models.File.objects.all():
            self.assertEqual(file.checksum, file.local_file_id)

    def test_contentnode_file_extension_data(self):
        for file in models.File.objects.all().prefetch_related('local_file'):
            self.assertEqual(file.extension, file.local_file.extension)

    def test_contentnode_file_size_data(self):
        for file in models.File.objects.all().prefetch_related('local_file'):
            self.assertEqual(file.file_size, file.local_file.file_size)

    def test_channel_icon_encoding(self):
        self.assertIsNotNone(self.content_channel.icon_encoding)


class ChannelExportUtilityFunctionTestCase(StudioTestCase):
    @classmethod
    def setUpClass(cls):
        super(ChannelExportUtilityFunctionTestCase, cls).setUpClass()
        cls.patch_copy_db = patch('contentcuration.utils.publish.save_export_database')
        cls.patch_copy_db.start()

    @classmethod
    def tearDownClass(cls):
        super(ChannelExportUtilityFunctionTestCase, cls).tearDownClass()
        cls.patch_copy_db.stop()

    def setUp(self):
        super(ChannelExportUtilityFunctionTestCase, self).setUp()
        fh, output_db = tempfile.mkstemp(suffix=".sqlite3")
        self.output_db = output_db
        set_active_content_database(self.output_db)
        prepare_export_database(self.output_db)

    def tearDown(self):
        set_active_content_database(None)
        if os.path.exists(self.output_db):
            os.remove(self.output_db)
        if self.output_db in connections.databases:
            del connections.databases[self.output_db]
        super(ChannelExportUtilityFunctionTestCase, self).tearDown()

    def test_convert_channel_thumbnail_empty_thumbnail(self):
        channel = cc.Channel.objects.create()
        self.assertEqual("", convert_channel_thumbnail(channel))

    def test_convert_channel_thumbnail_static_thumbnail(self):
        channel = cc.Channel.objects.create(thumbnail="/static/kolibri_flapping_bird.png")
        self.assertEqual("", convert_channel_thumbnail(channel))

    def test_convert_channel_thumbnail_encoding_valid(self):
        channel = cc.Channel.objects.create(thumbnail="/content/kolibri_flapping_bird.png", thumbnail_encoding={"base64": "flappy_bird"})
        self.assertEqual("flappy_bird", convert_channel_thumbnail(channel))

    def test_convert_channel_thumbnail_encoding_invalid(self):
        with patch("contentcuration.utils.publish.get_thumbnail_encoding", return_value="this is a test"):
            channel = cc.Channel.objects.create(thumbnail="/content/kolibri_flapping_bird.png", thumbnail_encoding={})
            self.assertEquals("this is a test", convert_channel_thumbnail(channel))

    def test_create_slideshow_manifest(self):
        content_channel = cc.Channel.objects.create()
        ccnode = cc.ContentNode.objects.create(kind_id=slideshow(), extra_fields={})
        kolibrinode = create_bare_contentnode(ccnode, ccnode.language, content_channel.id, content_channel.name)
        create_slideshow_manifest(ccnode, kolibrinode)
        manifest_collection = cc.File.objects.filter(contentnode=ccnode, preset_id=u"slideshow_manifest")
        assert len(manifest_collection) == 1


class ChannelExportPrerequisiteTestCase(StudioTestCase):
    @classmethod
    def setUpClass(cls):
        super(ChannelExportPrerequisiteTestCase, cls).setUpClass()
        cls.patch_copy_db = patch('contentcuration.utils.publish.save_export_database')
        cls.patch_copy_db.start()

    def setUp(self):
        super(ChannelExportPrerequisiteTestCase, self).setUp()
        fh, output_db = tempfile.mkstemp(suffix=".sqlite3")
        self.output_db = output_db
        set_active_content_database(self.output_db)
        prepare_export_database(self.output_db)

    def tearDown(self):
        super(ChannelExportPrerequisiteTestCase, self).tearDown()
        set_active_content_database(None)
        if self.output_db in connections.databases:
            del connections.databases[self.output_db]
        if os.path.exists(self.output_db):
            os.remove(self.output_db)

    def test_nonexistent_prerequisites(self):
        channel = cc.Channel.objects.create()
        node1 = cc.ContentNode.objects.create(kind_id="exercise", parent_id=channel.main_tree.pk)
        exercise = cc.ContentNode.objects.create(kind_id="exercise")

        cc.PrerequisiteContentRelationship.objects.create(target_node=exercise, prerequisite=node1)
        map_prerequisites(node1)


class ChannelExportPublishedData(StudioTestCase):
    def test_fill_published_fields(self):
        version_notes = description()
        channel = cc.Channel.objects.create()
        channel.last_published
        fill_published_fields(channel, version_notes)
        self.assertTrue(channel.published_data)
        self.assertIsNotNone(channel.published_data.get(0))
        self.assertEqual(channel.published_data[0]['version_notes'], version_notes)
