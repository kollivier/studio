# flake8: noqa
from .test_settings import *  # noqa

# These endpoints will throw an error on the django debug panel
EXCLUDED_DEBUG_URLS = [
    "/content/storage",
]


def custom_show_toolbar(request):
    return not any(request.path.startswith(url) for url in EXCLUDED_DEBUG_URLS)


LANGUAGES += (('ar', ugettext('Arabic')),)  # noqa

try:
    import debug_panel  # noqa
except ImportError:
    # no debug panel, no use trying to add it to our middleware
    pass
else:
    # if debug_panel exists, add it to our INSTALLED_APPS
    INSTALLED_APPS += ('debug_panel', 'debug_toolbar', 'pympler')
    MIDDLEWARE_CLASSES += ('debug_panel.middleware.DebugPanelMiddleware',)
    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': custom_show_toolbar,

        # When enabled, these settings significantly slow down page loads.
        # It may be useful to temporarily enable them for specific debugging tasks,
        # like template debugging or issues with SQL queries / caching.
        # This URL has more details on each specific option:
        # https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html
        'RENDER_PANELS': False,
        'ENABLE_STACKTRACES': False,
        'SHOW_TEMPLATE_CONTEXT': False
    }

DEBUG_TOOLBAR_PANELS = [
    'debug_toolbar.panels.versions.VersionsPanel',
    'debug_toolbar.panels.profiling.ProfilingPanel',
    'debug_toolbar.panels.timer.TimerPanel',
    'debug_toolbar.panels.settings.SettingsPanel',
    'debug_toolbar.panels.headers.HeadersPanel',
    'debug_toolbar.panels.request.RequestPanel',
    'debug_toolbar.panels.sql.SQLPanel',
    'debug_toolbar.panels.staticfiles.StaticFilesPanel',
    'debug_toolbar.panels.templates.TemplatesPanel',
    'debug_toolbar.panels.cache.CachePanel',
    'debug_toolbar.panels.signals.SignalsPanel',
    'debug_toolbar.panels.logging.LoggingPanel',
    'debug_toolbar.panels.redirects.RedirectsPanel',
]

AWS_AUTO_CREATE_BUCKET = True
