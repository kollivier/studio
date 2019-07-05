import sys


if 'post_build' in sys.argv:
    if sys.platform == 'darwin':
        app_path = 'dist/osx/Kolibri Studio.app'
