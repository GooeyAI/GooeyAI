from decimal import Decimal

from django.db import migrations

# values of AIModelSpec.Categories, ModelProvider, ModelSku and ModelCategory,
# frozen for this migration
LLM, ASR = 3, 5
GOOGLE = 2
LLM_PROMPT, LLM_COMPLETION, ASR_AUDIO_SECONDS = 1, 2, 11
PRICING_LLM, PRICING_SPEECH_RECOGNITION = 1, 7

PRICING_URL = "https://cloud.google.com/vertex-ai/generative-ai/pricing"

# model_id, model_name, sku, unit_cost, unit_quantity, category, notes
PRICING = [
    (
        "gemini-3.5-transcribe",
        "Gemini 3.5 Transcribe",
        ASR_AUDIO_SECONDS,
        "0.005",
        60,
        PRICING_SPEECH_RECOGNITION,
        "estimate: $2/1M audio input tokens + $12/1M output tokens, about $0.005 an audio minute",
    ),
    (
        "gemini-3.8-live",
        "Gemini 3.8 Live",
        LLM_PROMPT,
        "3",
        1_000_000,
        PRICING_LLM,
        "audio input tokens",
    ),
    (
        "gemini-3.8-live",
        "Gemini 3.8 Live",
        LLM_COMPLETION,
        "12",
        1_000_000,
        PRICING_LLM,
        "audio output tokens",
    ),
]

# name, label, model_id, pricing sku, extra fields
SPECS = [
    (
        "gemini_3_5_transcribe",
        "Gemini 3.5 Transcribe",
        "gemini-3.5-transcribe",
        ASR_AUDIO_SECONDS,
        dict(category=ASR),
    ),
    (
        "gemini_live_3_8",
        "Gemini 3.8 Live (Voice Only) • Google",
        "gemini-3.8-live",
        LLM_PROMPT,
        dict(
            category=LLM,
            version=3.8,
            llm_context_window=131_072,
            llm_max_output_tokens=65_536,
            llm_is_audio_model=True,
            llm_supports_temperature=False,
        ),
    ),
]


def add_gemini_transcribe_and_live_3_8(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    AIModelCreator = apps.get_model("ai_models", "AIModelCreator")
    AIModelSpec = apps.get_model("ai_models", "AIModelSpec")
    ModelPricing = apps.get_model("usage_costs", "ModelPricing")

    for model_id, name, sku, cost, unit_quantity, category, notes in PRICING:
        ModelPricing.objects.using(db_alias).update_or_create(
            model_id=model_id,
            sku=sku,
            defaults=dict(
                model_name=name,
                unit_cost=Decimal(cost),
                unit_quantity=unit_quantity,
                category=category,
                provider=GOOGLE,
                pricing_url=PRICING_URL,
                notes=notes,
            ),
        )

    google, _ = AIModelCreator.objects.using(db_alias).get_or_create(name="Google")
    for name, label, model_id, sku, fields in SPECS:
        pricing = (
            ModelPricing.objects.using(db_alias)
            .filter(model_id=model_id, sku=sku)
            .first()
        )
        # keep any spec an admin already made
        AIModelSpec.objects.using(db_alias).get_or_create(
            name=name,
            defaults=dict(
                label=label,
                creator=google,
                model_id=model_id,
                provider=GOOGLE,
                pricing=pricing,
                **fields,
            ),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("ai_models", "0014_asr_tts_model_specs"),
        ("usage_costs", "0045_asr_tts_pricing"),
    ]

    operations = [
        # no reverse: deleting a pricing row deletes the usage costs recorded on it
        migrations.RunPython(
            add_gemini_transcribe_and_live_3_8, migrations.RunPython.noop
        ),
    ]
