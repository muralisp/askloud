import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "askloud_gui.settings")
application = get_wsgi_application()
