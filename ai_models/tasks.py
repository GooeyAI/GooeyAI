from celery import shared_task

from ai_models import requesty


@shared_task
def sync_requesty_models():
    requesty.sync_requesty_models()
