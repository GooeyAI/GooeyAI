from django.apps import AppConfig


class ModelApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "model_api"
    verbose_name = "Model API"
