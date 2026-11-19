import importlib
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps

from ai_models.models import AIModelSpec
from gooey_gui.core.state import set_session_state
from bots.models import AppUser, SavedRun, Workflow
from daras_ai_v2.asr import AsrModels, get_asr_model, run_asr, wav_duration_seconds
from daras_ai_v2.text_to_speech_settings_widgets import TextToSpeechProviders
from recipes.TextToSpeech import (
    TextToSpeechPage,
    get_tts_model,
    tts_model_lookup,
)
from daras_ai_v2.base_v2 import format_credits_as_dollars
from recipes.VideoBots import VideoBotsPage, split_rounded_credits
from recipes.asr_page import AsrPage
from usage_costs.cost_utils import record_cost_auto
from usage_costs.models import ModelSku, UsageCost


@pytest.fixture
def asr_tts_pricing(transactional_db):
    """The pricing rows and AI models the data migrations add; tests run
    without migrations."""
    schema_editor = SimpleNamespace(connection=SimpleNamespace(alias="default"))
    pricing = importlib.import_module("usage_costs.migrations.0045_asr_tts_pricing")
    pricing.add_asr_tts_pricing(apps, schema_editor)
    ai_models = importlib.import_module("ai_models.migrations.0014_asr_tts_model_specs")
    ai_models.add_asr_tts_model_specs(apps, schema_editor)


@pytest.fixture
def user(transactional_db):
    return AppUser.objects.create(uid="test_user", is_anonymous=False)


def make_run(user, workflow, state):
    return SavedRun.objects.create(
        workflow=workflow, run_id="run", uid=user.uid, state=state
    )


def test_wav_duration_is_the_pcm_bytes_at_32000_a_second():
    assert wav_duration_seconds(44 + 32_000 * 90) == 90
    assert wav_duration_seconds(10) == 0


def asr_run(sr, selected_model: str, seconds: float, **patches):
    """Run ASR on a wav of `seconds`, with the provider calls in `patches`
    mocked, as the running saved run `sr`."""
    wav = ("gs://bucket/audio.wav", 44 + int(32_000 * seconds))
    with (
        patch("celeryapp.tasks.get_running_saved_run", return_value=sr),
        patch("daras_ai_v2.asr.audio_url_to_wav_url", return_value=wav),
        patch.multiple("daras_ai_v2.asr", **patches) if patches else nullcontext(),
    ):
        return run_asr("https://example.com/audio.mp3", selected_model)


INTRON = dict(intron_asr=MagicMock(return_value={"audio_transcript": "hi"}))


def test_api_asr_model_records_audio_seconds(asr_tts_pricing, user):
    sr = make_run(user, Workflow.ASR, {})
    assert asr_run(sr, "intron", 90, **INTRON) == "hi"
    [cost] = UsageCost.objects.filter(saved_run=sr)
    assert cost.pricing.model_id == "intron-voice"
    assert cost.pricing.sku == ModelSku.asr_audio_seconds
    # $0.17 a minute for 1.5 minutes
    assert float(cost.dollar_amount) == pytest.approx(0.255)


def test_modal_asr_model_records_gpu_time(asr_tts_pricing, user):
    sr = make_run(user, Workflow.ASR, {})
    sravaani = MagicMock()
    sravaani.return_value.run.remote.return_value = {"text": "hi"}
    with (
        patch("modal.Cls.from_name", return_value=sravaani),
        # an hour of GPU time
        patch("daras_ai_v2.asr.time.monotonic", side_effect=[0.0, 3600.0]),
    ):
        assert asr_run(sr, "sravaani_v1", 90) == "hi"
    [cost] = UsageCost.objects.filter(saved_run=sr)
    assert cost.pricing.sku == ModelSku.gpu_ms
    assert float(cost.dollar_amount) == pytest.approx(1.10)


def test_billing_does_not_use_the_display_pricing_link(asr_tts_pricing, user):
    # the AI model's pricing link is for display only
    AIModelSpec.objects.filter(name="intron").update(pricing=None)
    sr = make_run(user, Workflow.ASR, {})
    asr_run(sr, "intron", 90, **INTRON)
    [cost] = UsageCost.objects.filter(saved_run=sr)
    assert cost.pricing.model_id == "intron-voice"


@pytest.mark.parametrize(
    "selected_model, patches, reported",
    [
        # call_celery_task records its GPU time against the queue
        (
            "whisper_large_v2",
            dict(call_celery_task=MagicMock(return_value={"text": "hi"})),
            False,
        ),
        # no published price: keeps the per-word price, and Sentry hears of it
        (
            "ghana_nlp_asr_v2",
            dict(
                requests=MagicMock(
                    **{"post.return_value.json.return_value": {"text": "hi"}}
                ),
                raise_for_status=MagicMock(),
            ),
            True,
        ),
    ],
)
def test_asr_model_without_a_minute_price_records_nothing(
    asr_tts_pricing, user, selected_model, patches, reported
):
    sr = make_run(user, Workflow.ASR, {})
    with patch("sentry_sdk.capture_message") as capture_message:
        assert asr_run(sr, selected_model, 90, **patches) == "hi"
    assert not UsageCost.objects.filter(saved_run=sr).exists()
    assert capture_message.called == reported


def test_asr_run_is_charged_its_recorded_cost(asr_tts_pricing, user):
    state = {"output_text": ["hello world"], "selected_model": "intron"}
    sr = make_run(user, Workflow.ASR, state)
    # 10 minutes at $0.17
    asr_run(sr, "intron", 600, **INTRON)
    page = AsrPage(user=user, query_params=dict(run_id=sr.run_id, uid=user.uid))
    assert page.get_price_roundoff(state) == 170


@pytest.mark.parametrize(
    "provider, state, expected",
    [
        (TextToSpeechProviders.OPEN_AI, {}, dict(model_id="tts-1")),
        (
            TextToSpeechProviders.OPEN_AI,
            {"openai_tts_model": "tts_1_hd"},
            dict(model_id="tts-1-hd"),
        ),
        (TextToSpeechProviders.GOOGLE_TTS, {}, dict(model_id="Neural2")),
        (
            TextToSpeechProviders.GOOGLE_TTS,
            {"google_voice_name": "en-US-Studio-O"},
            dict(model_id="Studio"),
        ),
        (
            TextToSpeechProviders.GOOGLE_TTS,
            {"google_voice_name": "en-US-Chirp3-HD-Kore"},
            dict(model_id="Chirp3-HD"),
        ),
        (
            TextToSpeechProviders.GOOGLE_TTS,
            {"google_voice_name": "en-IN-Wavenet-A"},
            dict(model_id="Wavenet"),
        ),
        (TextToSpeechProviders.GEMINI_TTS, {}, dict(model_id="gemini-3.8-flash-tts")),
        (TextToSpeechProviders.SARVAM, {}, dict(name="bulbul_v3")),
        (TextToSpeechProviders.INTRON, {}, dict(name="sahara_v2_5")),
        (
            TextToSpeechProviders.OPEN_AI,
            {"openai_tts_model": "gpt_4_o_mini"},
            dict(model_id="gpt-4o-mini-tts"),
        ),
        # no pricing row: no published price
        (TextToSpeechProviders.GHANA_NLP, {}, dict(name="ghana_nlp_tts")),
    ],
)
def test_tts_model_filters(provider, state, expected):
    assert tts_model_lookup(provider, state) == expected


@pytest.mark.parametrize(
    "provider, state, expected",
    [
        (
            TextToSpeechProviders.GOOGLE_TTS,
            {"google_voice_name": "en-US-Studio-O"},
            "google_tts_studio",
        ),
        (TextToSpeechProviders.SARVAM, {}, "bulbul_v3"),
        (TextToSpeechProviders.ELEVEN_LABS, {}, None),
    ],
)
def test_get_tts_model(asr_tts_pricing, provider, state, expected):
    tts_model = get_tts_model(provider, state)
    assert (tts_model and tts_model.name) == expected


def test_azure_hd_voices_have_their_own_price():
    voices = {
        "ava": {"ShortName": "en-US-Ava:DragonHDLatestNeural"},
        "jenny": {"ShortName": "en-US-JennyNeural"},
    }
    with patch("recipes.TextToSpeech.azure_tts_voices", return_value=voices):
        provider = TextToSpeechProviders.AZURE_TTS
        assert tts_model_lookup(provider, {"azure_voice_name": "ava"}) == dict(
            model_id="neural-hd"
        )
        assert tts_model_lookup(provider, {"azure_voice_name": "jenny"}) == dict(
            model_id="neural"
        )


def test_tts_run_records_and_is_charged_its_characters(asr_tts_pricing, user):
    state = {
        "tts_provider": "GOOGLE_TTS",
        "google_voice_name": "en-US-Studio-O",
        "text_prompt": "x" * 100_000,
    }
    sr = make_run(user, Workflow.TEXT_TO_SPEECH, state)
    page = TextToSpeechPage(
        user=user, query_params=dict(run_id=sr.run_id, uid=user.uid)
    )
    with (
        patch("celeryapp.tasks.get_running_saved_run", return_value=sr),
        patch("google.cloud.texttospeech.TextToSpeechClient"),
        patch("recipes.TextToSpeech.upload_file_from_bytes", return_value="url"),
    ):
        list(page.run(state))
    [cost] = UsageCost.objects.filter(saved_run=sr)
    assert cost.pricing.model_id == "Studio"
    # $160 for 1M characters: $16 for 100K
    assert page.get_price_roundoff(state) == 1600


def test_elevenlabs_tts_keeps_its_own_price(asr_tts_pricing, user):
    state = {"tts_provider": "ELEVEN_LABS", "text_prompt": "x" * 1000}
    sr = make_run(user, Workflow.TEXT_TO_SPEECH, state)
    page = TextToSpeechPage(
        user=user, query_params=dict(run_id=sr.run_id, uid=user.uid)
    )
    assert page.get_price_roundoff(state) == 79


def test_tts_without_a_price_keeps_the_flat_price(asr_tts_pricing, user):
    state = {"tts_provider": "GHANA_NLP", "text_prompt": "hello"}
    sr = make_run(user, Workflow.TEXT_TO_SPEECH, state)
    page = TextToSpeechPage(
        user=user, query_params=dict(run_id=sr.run_id, uid=user.uid)
    )
    assert page.get_price_roundoff(state) == page.price


def test_agent_notes_list_speech_costs_apart_from_the_llm(asr_tts_pricing, user):
    sr = make_run(user, Workflow.VIDEO_BOTS, {"tts_provider": "GOOGLE_TTS"})
    with patch("celeryapp.tasks.get_running_saved_run", return_value=sr):
        record_cost_auto("chirp_3", ModelSku.asr_audio_seconds, 600)
        record_cost_auto("Studio", ModelSku.tts_characters, 100_000)
    page = VideoBotsPage(user=user, query_params=dict(run_id=sr.run_id, uid=user.uid))
    assert page.get_speech_credits() == {
        # 10 minutes at $0.016
        "Chirp 3": pytest.approx(16),
        # 100K characters at $160 / 1M
        "Google Studio": pytest.approx(1600),
    }
    # the cost note takes the speech parts out of the LLM's part
    set_session_state({"selected_model": "gpt_4_o"})
    parts = dict(page.get_cost_parts())
    assert parts["Chirp 3"] == 16
    assert parts["Google Studio"] == 1600


@pytest.mark.parametrize(
    "voice_name, model_id",
    [
        ("en-IN-Chirp3-HD-Aoede", "Chirp3-HD"),
        ("en-US-Studio-O", "Studio"),
        ("cmn-CN-Wavenet-A", "Wavenet"),
        ("en-US-Neural2-F", "Neural2"),
        ("en-US-Journey-D", "Chirp3-HD"),
        # a type with no price of its own: the run keeps the flat price
        ("en-US-News-K", None),
        # a type name that is not the third part does not count
        ("en-US-Casual-Studio", None),
        # the run strips the voice name, and so does its price
        (" en-US-Studio-O ", "Studio"),
    ],
)
def test_google_model_id_from_voice_type(voice_name, model_id):
    state = {"google_voice_name": voice_name}
    lookup = model_id and dict(model_id=model_id)
    assert tts_model_lookup(TextToSpeechProviders.GOOGLE_TTS, state) == lookup


@pytest.mark.parametrize(
    "costs, expected",
    [
        # three costs under a credit round to one credit in all, not three
        (
            {"LLM": 0.13, "ASR": 0.06, "TTS": 0.09},
            [("LLM", 1), ("ASR", 0.06), ("TTS", 0.09)],
        ),
        # the leftover credits go to the largest fractions
        (
            {"LLM": 2.4, "ASR": 0.7, "TTS": 1.6},
            [("LLM", 2), ("ASR", 1), ("TTS", 2)],
        ),
        # float noise does not round up a whole total
        ({"LLM": 2.0000000001, "ASR": 1.0}, [("LLM", 2), ("ASR", 1)]),
    ],
)
def test_split_rounded_credits_add_up_to_the_rounded_total(costs, expected):
    assert split_rounded_credits(costs) == expected


def test_a_part_under_a_credit_shows_as_less_than_a_cent():
    assert format_credits_as_dollars(0.06) == "<$0.01"
    assert format_credits_as_dollars(3) == "$0.03"


@pytest.mark.parametrize(
    "api_key, tts_credits",
    [
        # 0.079 credits a character for 100 characters
        (None, 7.9),
        # the user's own ElevenLabs key: no TTS charge
        ("my-key", 0),
    ],
)
def test_elevenlabs_agent_pays_its_tts_by_characters(
    asr_tts_pricing, user, api_key, tts_credits
):
    state = {
        "tts_provider": "ELEVEN_LABS",
        "elevenlabs_api_key": api_key,
        "raw_tts_text": ["x" * 100],
    }
    sr = make_run(user, Workflow.VIDEO_BOTS, state)
    page = VideoBotsPage(user=user, query_params=dict(run_id=sr.run_id, uid=sr.uid))
    # no usage recorded: 1 credit, plus 3 per run
    assert page.get_raw_price(state) == pytest.approx(1 + 3 + tts_credits)


def test_asr_model_is_found_among_asr_models_only(asr_tts_pricing):
    # an AI model of another kind with the same name is not the ASR model
    AIModelSpec.objects.filter(name="intron").update(
        category=AIModelSpec.Categories.audio
    )
    assert get_asr_model(AsrModels.intron) is None
