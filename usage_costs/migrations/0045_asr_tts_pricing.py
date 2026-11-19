from decimal import Decimal

from django.db import migrations

# values of ModelSku, ModelCategory and ModelProvider, frozen for this migration
GPU_MS, ASR_AUDIO_SECONDS, TTS_CHARACTERS = 3, 11, 12
SPEECH_RECOGNITION, TEXT_TO_SPEECH = 7, 8
OPENAI, GOOGLE, AKS, MISTRAL, SARVAM, MODAL = 1, 2, 5, 9, 10, 15
REPLICATE, DEEPGRAM, AZURE_SPEECH, ELEVENLABS, INTRON, LELAPA = 19, 20, 21, 22, 23, 25

OPENAI_URL = "https://platform.openai.com/docs/pricing"
GOOGLE_ASR_URL = "https://cloud.google.com/speech-to-text/pricing"
GOOGLE_TTS_URL = "https://cloud.google.com/text-to-speech/pricing"
AZURE_URL = "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/"
SARVAM_URL = "https://www.sarvam.ai/api-pricing"
INTRON_URL = "https://voice.intron.io"
AKS_GPU = (
    "3.673",
    AKS,
    "https://azure.microsoft.com/en-in/pricing/details/virtual-machines/linux/#pricing",
    "NC24ads A100 v4 - 1 X A100 - Pay as you go - $3.6730/hour",
)
MODAL_A10G = ("1.10", MODAL, "https://modal.com/pricing", "Modal A10G")

# model_id, model_name, USD per audio minute, provider, pricing_url, notes
ASR_PER_MINUTE = [
    (
        "vaibhavs10/incredibly-fast-whisper",
        "Whisper Large v3",
        "0.001",
        REPLICATE,
        "https://replicate.com/vaibhavs10/incredibly-fast-whisper",
        "estimate: Replicate bills GPU time, about $0.001 for each audio minute",
    ),
    (
        "gpt-transcribe",
        "GPT Transcribe",
        "0.0045",
        OPENAI,
        "https://platform.openai.com/docs/pricing",
        "",
    ),
    (
        "gpt-4o-transcribe",
        "GPT-4o Transcribe",
        "0.006",
        OPENAI,
        "https://platform.openai.com/docs/pricing",
        "OpenAI's per-minute estimate; billed in audio tokens",
    ),
    (
        "gpt-4o-mini-transcribe",
        "GPT-4o mini Transcribe",
        "0.003",
        OPENAI,
        "https://platform.openai.com/docs/pricing",
        "OpenAI's per-minute estimate; billed in audio tokens",
    ),
    (
        "speech-v1",
        "Google Cloud V1",
        "0.024",
        GOOGLE,
        "https://cloud.google.com/speech-to-text/pricing",
        "$0.016 with data logging",
    ),
    (
        "chirp_3",
        "Chirp 3",
        "0.016",
        GOOGLE,
        "https://cloud.google.com/speech-to-text/pricing",
        "",
    ),
    (
        "nova",
        "Deepgram Nova",
        "0.0097",
        DEEPGRAM,
        "https://deepgram.com/pricing",
        "estimate: Nova-3 with diarization; the code sends tier=nova, model=general",
    ),
    (
        "azure-speech",
        "Azure Speech",
        "0.003",
        AZURE_SPEECH,
        "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/",
        "batch transcription",
    ),
    (
        "scribe_v1",
        "Scribe v1",
        "0.0033",
        ELEVENLABS,
        "https://elevenlabs.io/pricing/api",
        "Scribe v2 price; v1 is deprecated by ElevenLabs",
    ),
    (
        "saaras:v3",
        "Saaras v3",
        "0.0056",
        SARVAM,
        "https://www.sarvam.ai/api-pricing",
        "INR 0.49 / min at INR 88 / USD",
    ),
    (
        "voxtral-mini-2602",
        "Voxtral Mini Transcribe 2",
        "0.003",
        MISTRAL,
        "https://mistral.ai/pricing",
        "",
    ),
    (
        "lelapa-vulavula",
        "Vulavula",
        "0.005",
        LELAPA,
        "https://lelapa.ai/pricing",
        "estimate: $0.005 for each call",
    ),
    (
        "intron-voice",
        "Intron Voice",
        "0.17",
        INTRON,
        "https://voice.intron.io",
        "Intron audio transcription rate, billed from audio duration",
    ),
]

# model_id, model_name, USD per 1M characters, provider, pricing_url, notes
TTS_PER_MILLION_CHARS = [
    (
        "tts-1",
        "tts-1",
        "15",
        OPENAI,
        "https://platform.openai.com/docs/pricing",
        "",
    ),
    (
        "tts-1-hd",
        "tts-1-hd",
        "30",
        OPENAI,
        "https://platform.openai.com/docs/pricing",
        "",
    ),
    (
        "gpt-4o-mini-tts",
        "gpt-4o-mini-tts",
        "18",
        OPENAI,
        "https://platform.openai.com/docs/pricing",
        "estimate from audio tokens",
    ),
    (
        "Standard",
        "Google Standard",
        "4",
        GOOGLE,
        "https://cloud.google.com/text-to-speech/pricing",
        "",
    ),
    (
        "Wavenet",
        "Google WaveNet",
        "4",
        GOOGLE,
        "https://cloud.google.com/text-to-speech/pricing",
        "",
    ),
    (
        "Neural2",
        "Google Neural2",
        "16",
        GOOGLE,
        "https://cloud.google.com/text-to-speech/pricing",
        "also Polyglot voices",
    ),
    (
        "Chirp3-HD",
        "Google Chirp 3 HD",
        "30",
        GOOGLE,
        "https://cloud.google.com/text-to-speech/pricing",
        "also Chirp HD and Journey voices",
    ),
    (
        "Studio",
        "Google Studio",
        "160",
        GOOGLE,
        "https://cloud.google.com/text-to-speech/pricing",
        "",
    ),
    (
        "neural",
        "Azure Neural",
        "15",
        AZURE_SPEECH,
        "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/",
        "",
    ),
    (
        "neural-hd",
        "Azure Neural HD",
        "22",
        AZURE_SPEECH,
        "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/",
        "",
    ),
    (
        "gemini-3.8-flash-tts",
        "Gemini 3.8 Flash TTS",
        "16.5",
        GOOGLE,
        "https://cloud.google.com/text-to-speech/pricing",
        "estimate from tokens; doubles to 33 on 2027-01-01",
    ),
    (
        "gemini-3.8-flash-lite-tts",
        "Gemini 3.8 Flash-Lite TTS",
        "11",
        GOOGLE,
        "https://cloud.google.com/text-to-speech/pricing",
        "estimate from tokens; doubles to 22 on 2027-01-01",
    ),
    (
        "bulbul:v3",
        "Bulbul v3",
        "34",
        SARVAM,
        "https://www.sarvam.ai/api-pricing",
        "INR 3.00 / 10K chars at INR 88 / USD",
    ),
    (
        "sahara-v2.5",
        "Sahara v2.5",
        "20",
        INTRON,
        "https://voice.intron.io",
        "estimate: Intron publishes no TTS price",
    ),
]

# queue (= model_id), model_name, category, (USD per GPU-hour, provider, pricing_url, notes)
GPU_QUEUES = [
    (
        "gooey-gpu/short/openai/whisper-large-v2",
        "Whisper Large v2",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    (
        "gooey-gpu/long/openai/whisper-large-v2",
        "Whisper Large v2",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    (
        "gooey-gpu/short/Sunbird/asr-whisper-large-v3-salt",
        "Sunbird Ugandan Whisper v3",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    (
        "gooey-gpu/long/Sunbird/asr-whisper-large-v3-salt",
        "Sunbird Ugandan Whisper v3",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    (
        "gooey-gpu/short/akera/whisper-large-v3-kik-full_v2",
        "Kikuyu v2 Whisper",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    (
        "gooey-gpu/long/akera/whisper-large-v3-kik-full_v2",
        "Kikuyu v2 Whisper",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    (
        "gooey-gpu/short/Jacaranda-Health/ASR-STT",
        "Swahili Whisper v3",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    (
        "gooey-gpu/long/Jacaranda-Health/ASR-STT",
        "Swahili Whisper v3",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    (
        "gooey-gpu/facebook/seamless-m4t-v2-large",
        "Seamless M4T v2",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    (
        "gooey-gpu/mbazaNLP/stt_rw_sw_lg_conformer_ctc_large",
        "Mbaza Conformer LG",
        SPEECH_RECOGNITION,
        AKS_GPU,
    ),
    ("gooey-gpu/facebook/mms-1b-all", "MMS 1B", SPEECH_RECOGNITION, AKS_GPU),
    ("omniASR_LLM_7B", "Omnilingual ASR LLM 7B", SPEECH_RECOGNITION, MODAL_A10G),
    ("ARTPARK-IISc/SraVaani-1.0", "SraVaani 1.0", SPEECH_RECOGNITION, MODAL_A10G),
    ("gooey-gpu/bark", "Bark", TEXT_TO_SPEECH, AKS_GPU),
    ("mms-tts", "MMS TTS", TEXT_TO_SPEECH, MODAL_A10G),
]


def add_asr_tts_pricing(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ModelPricing = apps.get_model("usage_costs", "ModelPricing")
    rows = (
        [
            (model_id, name, ASR_AUDIO_SECONDS, 60, SPEECH_RECOGNITION, *price)
            for model_id, name, *price in ASR_PER_MINUTE
        ]
        + [
            (model_id, name, TTS_CHARACTERS, 1_000_000, TEXT_TO_SPEECH, *price)
            for model_id, name, *price in TTS_PER_MILLION_CHARS
        ]
        + [
            (model_id, name, GPU_MS, 3_600_000, category, *gpu)
            for model_id, name, category, gpu in GPU_QUEUES
        ]
    )
    for (
        model_id,
        name,
        sku,
        unit_quantity,
        category,
        cost,
        provider,
        url,
        notes,
    ) in rows:
        ModelPricing.objects.using(db_alias).update_or_create(
            model_id=model_id,
            sku=sku,
            defaults=dict(
                model_name=name,
                unit_cost=Decimal(cost),
                unit_quantity=unit_quantity,
                category=category,
                provider=provider,
                pricing_url=url,
                notes=notes,
            ),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("ai_models", "0012_asr_tts_providers"),
        ("usage_costs", "0044_asr_tts_skus"),
    ]

    operations = [
        # no reverse: deleting a pricing row deletes the usage costs recorded on it
        migrations.RunPython(add_asr_tts_pricing, migrations.RunPython.noop),
    ]
