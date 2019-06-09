import logging

from django.apps import AppConfig
from django.conf import settings

if not settings.DESKTOP_MODE and settings.AWS_AUTO_CREATE_BUCKET:
    from contentcuration.utils.minio_utils import ensure_storage_bucket_public


class ContentConfig(AppConfig):
    name = 'contentcuration'

    def ready(self):
        from django.db import connection

        if connection.vendor == "sqlite":
            cursor = connection.cursor()

            # http://www.sqlite.org/wal.html
            # WAL's main advantage allows simultaneous reads
            # and writes (vs. the default exclusive write lock)
            # at the cost of a slight penalty to all reads.
            cursor.execute("PRAGMA journal_mode=WAL;")
            logging.info("Enabled WAL Sqlite journaling mode...")
        # see note in the celery_signals.py file for why we import here.
        import contentcuration.utils.celery_signals
        if not settings.DESKTOP_MODE and settings.AWS_AUTO_CREATE_BUCKET:
            ensure_storage_bucket_public()
