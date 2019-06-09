from __future__ import absolute_import

import logging
import os

from celery import Celery
from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'contentcuration.settings')

app = Celery('contentcuration')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings', namespace='CELERY')

if settings.DESKTOP_MODE:
    # If we're running on the desktop, just use the filesystem broker as
    # we expect low volume of requests.
    celery_files_dir = os.path.join(settings.DATA_DIR, 'celery_broker')
    celery_out_dir = os.path.join(celery_files_dir, 'out')
    celery_processed_dir = os.path.join(celery_files_dir, 'processed')

    if not os.path.exists(celery_out_dir):
        os.makedirs(celery_out_dir)
    if not os.path.exists(celery_processed_dir):
        os.makedirs(celery_processed_dir)

    app.conf.update({
        'broker_url': 'filesystem://',
        'broker_transport_options': {
            'data_folder_in': celery_out_dir,
            'data_folder_out': celery_out_dir,
            'data_folder_processed': celery_processed_dir
        },
        'imports': ('tasks',),
        'result_persistent': False,
        'task_serializer': 'json',
        'result_serializer': 'json',
        'accept_content': ['json']
    })

if not settings.DESKTOP_MODE:
    import django
    django.setup()
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS, force=True)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
