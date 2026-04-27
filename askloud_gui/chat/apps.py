from django.apps import AppConfig


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chat"

    def ready(self):
        """
        Initialise the Askloud engine once when Django starts.
        The engine loads data/ and config/ from ASKLOUD_BASE_DIR.
        """
        from django.conf import settings
        from .engine_wrapper import EngineManager

        mgr = EngineManager.get()
        mgr.initialize(settings.ASKLOUD_BASE_DIR)
