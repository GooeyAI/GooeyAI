from django.db import migrations

# values of AIModelSpec.Categories, ModelProvider and ModelSku, frozen for this
# migration
ASR, TTS = 5, 6
OPENAI, GOOGLE, AKS, MISTRAL, SARVAM, MODAL = 1, 2, 5, 9, 10, 15
REPLICATE, DEEPGRAM, AZURE_SPEECH, ELEVENLABS, INTRON = 19, 20, 21, 22, 23
GHANA_NLP, LELAPA, MANSA, UBERDUCK = 24, 25, 26, 27
GPU_MS, ASR_AUDIO_SECONDS, TTS_CHARACTERS = 3, 11, 12

# the creators of the speech models and their logos; a creator that already
# exists keeps its logo
CREATOR_PHOTOS = {
    "Deepgram": "https://avatars.githubusercontent.com/u/17422641?s=200&v=4",
    "ElevenLabs": "https://avatars.githubusercontent.com/u/94471909?s=200&v=4",
    "Intron": "https://avatars.githubusercontent.com/u/67436070?s=200&v=4",
    "GhanaNLP": "https://avatars.githubusercontent.com/u/59252568?s=200&v=4",
    "Lelapa AI": "https://avatars.githubusercontent.com/u/121013311?s=200&v=4",
    "Suno": "https://avatars.githubusercontent.com/u/99442120?s=200&v=4",
    "Uberduck": "https://avatars.githubusercontent.com/u/88852722?s=200&v=4",
    "MbazaNLP": "https://cdn-avatars.huggingface.co/v1/production/uploads/1659948950838-60bb7e3129800c34660339e4.png",
}

# name, label, creator, model_id, provider, (pricing model_id, sku) or None.
# The name is the model's key in the API: the ASR `selected_model`, or the TTS
# model or provider. gpt_4_o_audio, gpt_4_o_mini_audio and the TTS gpt_4_o_mini
# are names of LLM specs, so those three use their OpenAI model names instead.
ASR_SPECS = [
    # billed by audio minute
    (
        "whisper_large_v3",
        "Whisper Large v3",
        "OpenAI",
        "vaibhavs10/incredibly-fast-whisper",
        REPLICATE,
        ("vaibhavs10/incredibly-fast-whisper", ASR_AUDIO_SECONDS),
    ),
    (
        "gpt_transcribe",
        "GPT Transcribe",
        "OpenAI",
        "gpt-transcribe",
        OPENAI,
        ("gpt-transcribe", ASR_AUDIO_SECONDS),
    ),
    (
        "gpt_4o_transcribe",
        "GPT-4o Transcribe",
        "OpenAI",
        "gpt-4o-transcribe",
        OPENAI,
        ("gpt-4o-transcribe", ASR_AUDIO_SECONDS),
    ),
    (
        "gpt_4o_mini_transcribe",
        "GPT-4o mini Transcribe",
        "OpenAI",
        "gpt-4o-mini-transcribe",
        OPENAI,
        ("gpt-4o-mini-transcribe", ASR_AUDIO_SECONDS),
    ),
    (
        "gcp_v1",
        "Google Cloud V1",
        "Google",
        "speech-v1",
        GOOGLE,
        ("speech-v1", ASR_AUDIO_SECONDS),
    ),
    (
        "chirp_3",
        "Chirp 3",
        "Google",
        "chirp_3",
        GOOGLE,
        ("chirp_3", ASR_AUDIO_SECONDS),
    ),
    (
        "deepgram",
        "Deepgram Nova",
        "Deepgram",
        "nova",
        DEEPGRAM,
        ("nova", ASR_AUDIO_SECONDS),
    ),
    (
        "azure",
        "Azure Speech",
        "Microsoft",
        "azure-speech",
        AZURE_SPEECH,
        ("azure-speech", ASR_AUDIO_SECONDS),
    ),
    (
        "elevenlabs",
        "Scribe v1",
        "ElevenLabs",
        "scribe_v1",
        ELEVENLABS,
        ("scribe_v1", ASR_AUDIO_SECONDS),
    ),
    (
        "saaras_v3",
        "Saaras v3",
        "Sarvam AI",
        "saaras:v3",
        SARVAM,
        ("saaras:v3", ASR_AUDIO_SECONDS),
    ),
    (
        "voxtral_mini",
        "Voxtral Mini Transcribe 2",
        "Mistral",
        "voxtral-mini-2602",
        MISTRAL,
        ("voxtral-mini-2602", ASR_AUDIO_SECONDS),
    ),
    (
        "lelapa",
        "Vulavula",
        "Lelapa AI",
        "lelapa-vulavula",
        LELAPA,
        ("lelapa-vulavula", ASR_AUDIO_SECONDS),
    ),
    (
        "intron",
        "Intron Voice",
        "Intron",
        "intron-voice",
        INTRON,
        ("intron-voice", ASR_AUDIO_SECONDS),
    ),
    # ASR with no published price
    (
        "ghana_nlp_asr_v2",
        "Ghana NLP ASR v2",
        "GhanaNLP",
        "ghana-nlp-asr-v2",
        GHANA_NLP,
        None,
    ),
    (
        "mansa",
        "Mansa Transcribe",
        "African Languages Lab",
        "mansa-transcribe",
        MANSA,
        None,
    ),
    # ASR on our GPUs, billed by GPU time; short and long files share a price
    (
        "whisper_large_v2",
        "Whisper Large v2",
        "OpenAI",
        "openai/whisper-large-v2",
        AKS,
        ("gooey-gpu/short/openai/whisper-large-v2", GPU_MS),
    ),
    (
        "whisper_sunbird_large_v3",
        "Sunbird Ugandan Whisper v3",
        "Sunbird AI",
        "Sunbird/asr-whisper-large-v3-salt",
        AKS,
        ("gooey-gpu/short/Sunbird/asr-whisper-large-v3-salt", GPU_MS),
    ),
    (
        "whisper_akera_large_v3",
        "Kikuyu v2 Whisper",
        "akera",
        "akera/whisper-large-v3-kik-full_v2",
        AKS,
        ("gooey-gpu/short/akera/whisper-large-v3-kik-full_v2", GPU_MS),
    ),
    (
        "whisper_swahili_medium_v3",
        "Swahili Whisper v3",
        "Jacaranda",
        "Jacaranda-Health/ASR-STT",
        AKS,
        ("gooey-gpu/short/Jacaranda-Health/ASR-STT", GPU_MS),
    ),
    (
        "seamless_m4t_v2",
        "Seamless M4T v2",
        "Meta AI",
        "facebook/seamless-m4t-v2-large",
        AKS,
        ("gooey-gpu/facebook/seamless-m4t-v2-large", GPU_MS),
    ),
    (
        "mbaza_ctc_large",
        "Mbaza Conformer LG",
        "MbazaNLP",
        "mbazaNLP/stt_rw_sw_lg_conformer_ctc_large",
        AKS,
        ("gooey-gpu/mbazaNLP/stt_rw_sw_lg_conformer_ctc_large", GPU_MS),
    ),
    (
        "mms_1b_all",
        "MMS 1B",
        "Meta AI",
        "facebook/mms-1b-all",
        AKS,
        ("gooey-gpu/facebook/mms-1b-all", GPU_MS),
    ),
    (
        "meta_omnilingual_asr_llm_7b",
        "Omnilingual ASR LLM 7B",
        "Meta AI",
        "omniASR_LLM_7B",
        MODAL,
        ("omniASR_LLM_7B", GPU_MS),
    ),
    (
        "sravaani_v1",
        "SraVaani 1.0",
        "ARTPARK IISc",
        "ARTPARK-IISc/SraVaani-1.0",
        MODAL,
        ("ARTPARK-IISc/SraVaani-1.0", GPU_MS),
    ),
]

TTS_SPECS = [
    # billed by character; one Google spec for each voice type
    (
        "tts_1",
        "tts-1",
        "OpenAI",
        "tts-1",
        OPENAI,
        ("tts-1", TTS_CHARACTERS),
    ),
    (
        "tts_1_hd",
        "tts-1-hd",
        "OpenAI",
        "tts-1-hd",
        OPENAI,
        ("tts-1-hd", TTS_CHARACTERS),
    ),
    (
        "gpt_4o_mini_tts",
        "gpt-4o-mini-tts",
        "OpenAI",
        "gpt-4o-mini-tts",
        OPENAI,
        ("gpt-4o-mini-tts", TTS_CHARACTERS),
    ),
    (
        "google_tts_standard",
        "Google Standard",
        "Google",
        "Standard",
        GOOGLE,
        ("Standard", TTS_CHARACTERS),
    ),
    (
        "google_tts_wavenet",
        "Google WaveNet",
        "Google",
        "Wavenet",
        GOOGLE,
        ("Wavenet", TTS_CHARACTERS),
    ),
    (
        "google_tts_neural2",
        "Google Neural2",
        "Google",
        "Neural2",
        GOOGLE,
        ("Neural2", TTS_CHARACTERS),
    ),
    (
        "google_tts_chirp3_hd",
        "Google Chirp 3 HD",
        "Google",
        "Chirp3-HD",
        GOOGLE,
        ("Chirp3-HD", TTS_CHARACTERS),
    ),
    (
        "google_tts_studio",
        "Google Studio",
        "Google",
        "Studio",
        GOOGLE,
        ("Studio", TTS_CHARACTERS),
    ),
    (
        "azure_tts_neural",
        "Azure Neural",
        "Microsoft",
        "neural",
        AZURE_SPEECH,
        ("neural", TTS_CHARACTERS),
    ),
    (
        "azure_tts_neural_hd",
        "Azure Neural HD",
        "Microsoft",
        "neural-hd",
        AZURE_SPEECH,
        ("neural-hd", TTS_CHARACTERS),
    ),
    (
        "gemini_3_8_flash_tts",
        "Gemini 3.8 Flash TTS",
        "Google",
        "gemini-3.8-flash-tts",
        GOOGLE,
        ("gemini-3.8-flash-tts", TTS_CHARACTERS),
    ),
    (
        "gemini_3_8_flash_lite_tts",
        "Gemini 3.8 Flash-Lite TTS",
        "Google",
        "gemini-3.8-flash-lite-tts",
        GOOGLE,
        ("gemini-3.8-flash-lite-tts", TTS_CHARACTERS),
    ),
    (
        "bulbul_v3",
        "Bulbul v3",
        "Sarvam AI",
        "bulbul:v3",
        SARVAM,
        ("bulbul:v3", TTS_CHARACTERS),
    ),
    (
        "sahara_v2_5",
        "Sahara v2.5",
        "Intron",
        "sahara-v2.5",
        INTRON,
        ("sahara-v2.5", TTS_CHARACTERS),
    ),
    # TTS on GPUs, billed by GPU time
    ("bark", "Bark", "Suno", "bark", AKS, ("gooey-gpu/bark", GPU_MS)),
    ("mms_tts", "MMS TTS", "Meta AI", "mms-tts", MODAL, ("mms-tts", GPU_MS)),
    # TTS that keeps its own price, or has no published price
    (
        "eleven_multilingual_v2",
        "ElevenLabs Multilingual v2",
        "ElevenLabs",
        "eleven_multilingual_v2",
        ELEVENLABS,
        None,
    ),
    (
        "eleven_turbo_v2",
        "ElevenLabs Turbo v2",
        "ElevenLabs",
        "eleven_turbo_v2",
        ELEVENLABS,
        None,
    ),
    ("ghana_nlp_tts", "GhanaNLP TTS", "GhanaNLP", "ghana-nlp-tts", GHANA_NLP, None),
    ("uberduck", "Uberduck", "Uberduck", "uberduck", UBERDUCK, None),
]


def add_asr_tts_model_specs(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    AIModelSpec = apps.get_model("ai_models", "AIModelSpec")
    ModelPricing = apps.get_model("usage_costs", "ModelPricing")
    creators = speech_model_creators(apps, db_alias)
    specs = [(ASR, *spec) for spec in ASR_SPECS] + [(TTS, *spec) for spec in TTS_SPECS]
    for category, name, label, creator, model_id, provider, pricing_key in specs:
        pricing = None
        if pricing_key:
            pricing = (
                ModelPricing.objects.using(db_alias)
                .filter(model_id=pricing_key[0], sku=pricing_key[1])
                .first()
            )
        # keep any spec an admin already made
        AIModelSpec.objects.using(db_alias).get_or_create(
            name=name,
            defaults=dict(
                category=category,
                label=label,
                creator=creators[creator],
                model_id=model_id,
                provider=provider,
                pricing=pricing,
            ),
        )


def speech_model_creators(apps, db_alias) -> dict:
    """Every creator the specs name, by name; makes the missing ones."""
    AIModelCreator = apps.get_model("ai_models", "AIModelCreator")
    creators = {}
    for name in {spec[2] for spec in ASR_SPECS + TTS_SPECS}:
        creator, created = AIModelCreator.objects.using(db_alias).get_or_create(
            name=name, defaults=dict(photo_url=CREATOR_PHOTOS.get(name, ""))
        )
        if not created and not creator.photo_url and CREATOR_PHOTOS.get(name):
            creator.photo_url = CREATOR_PHOTOS[name]
            creator.save(update_fields=["photo_url"])
        creators[name] = creator
    return creators


class Migration(migrations.Migration):
    dependencies = [
        ("ai_models", "0013_asr_tts_categories"),
        ("usage_costs", "0045_asr_tts_pricing"),
    ]

    operations = [
        # no reverse: an admin can have edited or linked these specs
        migrations.RunPython(add_asr_tts_model_specs, migrations.RunPython.noop),
    ]
