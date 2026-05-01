from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "api"

    def ready(self) -> None:
        import importlib

        importlib.import_module("api.recurring.signals")
