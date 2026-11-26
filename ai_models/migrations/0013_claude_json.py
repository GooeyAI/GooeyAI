from django.db import migrations
from django.db.models import Q

LLM_CATEGORY = 3  # AIModelSpec.Categories.llm


def enable_claude_json(apps, schema_editor):
    """Every Claude LLM gets JSON mode, i.e. the json_output tool.

    Requesty specs were added with the default version of 1, which would force that
    tool on models that reject it (v5.1+), so they take the version of the direct
    spec they share a label with.
    """
    AIModelSpec = apps.get_model("ai_models", "AIModelSpec")
    db_alias = schema_editor.connection.alias
    claude = AIModelSpec.objects.using(db_alias).filter(
        Q(model_id__startswith="claude-")
        | Q(model_id__contains="/claude-")
        | Q(creator__website_url__icontains="anthropic"),
        category=LLM_CATEGORY,
    )
    versions = dict(
        claude.filter(version__gt=1).values_list("label", "version").order_by("version")
    )
    for spec in claude.filter(version=1, label__in=versions):
        spec.version = versions[spec.label]
        spec.save(update_fields=["version"])
    claude.update(llm_supports_json=True)


class Migration(migrations.Migration):
    dependencies = [
        ("ai_models", "0012_requesty_regions"),
    ]

    operations = [
        migrations.RunPython(enable_claude_json, migrations.RunPython.noop),
    ]
