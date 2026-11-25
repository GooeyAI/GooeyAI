from django.db import migrations

REQUESTY = 19  # ModelProvider.requesty


def clear_copied_router(apps, schema_editor):
    # the sync used to copy REQUESTY_API_KEY / REQUESTY_BASE_URL into every spec;
    # blank them so specs follow settings (and a rotated key) at run time
    db_alias = schema_editor.connection.alias
    AIModelSpec = apps.get_model("ai_models", "AIModelSpec")
    AIModelSpec.objects.using(db_alias).filter(provider=REQUESTY).update(
        api_key="", base_url=""
    )


class Migration(migrations.Migration):
    dependencies = [
        ("ai_models", "0013_aimodelspec_region_choices"),
    ]

    operations = [
        migrations.RunPython(clear_copied_router, migrations.RunPython.noop),
    ]
