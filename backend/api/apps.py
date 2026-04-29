from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "api"

    def ready(self) -> None:
        import importlib  # pylint: disable=import-outside-toplevel

        importlib.import_module("api.recurring_signals")
