import logging
import os
import sys
import time
try:
    from urllib2 import urlopen, URLError
except ModuleNotFoundError:
    from urllib.error import URLError
    from urllib.request import urlopen

# initialize logging before loading any third-party modules, as they may cause logging to get configured.
logging.basicConfig(level=logging.INFO)

import pew
import pew.ui

pew.set_app_name("Kolibri Studio")
logging.info("Entering main.py...")

script_dir = os.path.dirname(os.path.abspath(__file__))
app_root = os.path.join(script_dir, '..', 'contentcuration')
if hasattr(sys, 'frozen') and sys.frozen and sys.platform == 'darwin':
    # Since the app and the parent dir have the same name, packaging
    # contentcuration gives us the whole contentcuration root dir,
    # but for module resolution we want the actual Django app module.
    app_root = os.path.join(script_dir, 'lib', 'python2.7', 'contentcuration')

sys.path.append(script_dir)
sys.path.append(app_root)

files_dir = os.getenv('DATA_DIR') or pew.get_app_files_dir()
if not os.path.exists(files_dir):
    os.makedirs(files_dir)

os.environ["DJANGO_SETTINGS_MODULE"] = "contentcuration.dev_settings"
os.environ["RUN_MODE"] = "desktop"
os.environ["DATA_DIR"] = files_dir

from celery.bin import worker


def start_celery_worker():
    # Celery needs this to find the tasks module.
    sys.path.append(os.path.join(app_root, 'contentcuration'))

    from contentcuration.celery import app
    app_worker = worker.worker(app=app)
    options = {
        'app': 'contentcuration',
        # 'broker': app.config['CELERY_BROKER_URL'],
        'loglevel': 'INFO',
        'traceback': True,
    }
    app_worker.run(**options)
    logging.info("Starting Celery worker...")


def start_django():
    logging.info("Preparing Studio for launch...")

    # os.chdir(app_root)
    logging.info("Calling migrate...")
    from django.core.management import call_command
    call_command("migrate", interactive=False, database="default")

    # call_command("setup", interactive=False)

    logging.info("Starting server...")
    # from django.core.wsgi import get_wsgi_application
    # application = get_wsgi_application()
    call_command('runserver', '--noreload', '127.0.0.1:8084')


class Application(pew.ui.PEWApp):
    def setUp(self):
        """
        Start your UI and app run loop here.
        """

        # Set loading screen
        # loader_page = os.path.abspath(os.path.join('assets', '_load.html'))
        self.loader_url = "about:blank"  # 'file://{}'.format(loader_page)
        self.studio_loaded = False
        self.view = pew.ui.WebUIView("Kolibri Studio", self.loader_url, delegate=self)

        # start thread
        logging.info("Calling start thread...")
        self.thread = pew.ui.PEWThread(target=start_django)
        self.thread.daemon = True
        self.thread.start()

        self.load_thread = pew.ui.PEWThread(target=self.wait_for_server)
        self.load_thread.daemon = True
        self.load_thread.start()

        # make sure we show the UI before run completes, as otherwise
        # it is possible the run can complete before the UI is shown,
        # causing the app to shut down early
        self.view.show()
        return 0

    def page_loaded(self, url):
        """
        This is a PyEverywhere delegate method to let us know the WebView is ready to use.
        """

        # On Android, there is a system back button, that works like the browser back button. Make sure we clear the
        # history after first load so that the user cannot go back to the loading screen. We cannot clear the history
        # during load, so we do it here.
        # For more info, see: https://stackoverflow.com/questions/8103532/how-to-clear-webview-history-in-android
        if pew.ui.platform == 'android' and not self.studio_loaded and url != self.loader_url:
            # FIXME: Change pew to reference the native webview as webview.native_webview rather than webview.webview
            # for clarity.
            self.view.webview.webview.clearHistory()

        if not self.studio_loaded:
            self.studio_loaded = True

            self.worker_thread = pew.ui.PEWThread(target=start_celery_worker)
            self.worker_thread.daemon = True
            self.worker_thread.start()

    def wait_for_server(self):
        home_url = 'http://localhost:8084'

        # test url to see if servr has started
        def running():
            try:
                urlopen(home_url)
                return True
            except URLError:
                return False

        # Tie up this thread until the server is running
        while not running():
            logging.info('Kolibri Studio not yet started, checking again in one second...')
            time.sleep(1)

        # Check for saved URL, which exists when the app was put to sleep last time it ran
        saved_state = self.view.get_view_state()
        logging.debug('Persisted View State: {}'.format(self.view.get_view_state()))

        if "URL" in saved_state and saved_state["URL"].startswith(home_url):
            pew.ui.run_on_main_thread(self.view.load_url, saved_state["URL"])
            return

        pew.ui.run_on_main_thread(self.view.load_url, home_url)

    def get_main_window(self):
        return self.view

if __name__ == "__main__":
    import django
    django.setup()
    app = Application()
    app.run()
