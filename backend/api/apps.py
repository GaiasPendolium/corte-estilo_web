from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    verbose_name = 'API Peluquería'

    def ready(self):
        # Register signal handlers (e.g., seed admin on post_migrate).
        from . import signals  # noqa: F401
