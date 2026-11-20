import importlib
import io
import struct
import wave
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps

from ai_models.models import AIModelSpec
from bots.models import AppUser, SavedRun
from daras_ai_v2.asr import AsrModels, get_asr_model, run_asr, wav_duration_seconds
from daras_ai_v2.base_v2 import format_credits_as_dollars
from daras_ai_v2.text_to_speech_settings_widgets import TextToSpeechProviders
from gooey_gui.core.state import set_session_state
from recipes.TextToSpeech import TextToSpeechPage, get_tts_model, tts_model_lookup
from recipes.VideoBots import VideoBotsPage, split_rounded_credits
from recipes.asr_page import AsrPage
from usage_costs.cost_utils import record_cost_auto
from usage_costs.models import ModelSku, UsageCost

GOOGLE = TextToSpeechProviders.GOOGLE_TTS
INTRON = dict(intron_asr=MagicMock(return_value={"audio_transcript": "hi"}))


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


# ASR


@pytest.mark.parametrize("metadata_bytes", [0, 1_000_000])
def test_wav_duration_is_read_by_ffprobe(tmp_path, metadata_bytes):
    """Metadata chunks don't count as audio."""
    path = tmp_path / "audio.wav"
    path.write_bytes(wav_bytes(10, metadata_bytes))
    assert wav_duration_seconds(str(path), size=0) == pytest.approx(10)


def wav_bytes(seconds: float, metadata_bytes: int) -> bytes:
    """A 16 kHz mono 16-bit wav of silence, with a metadata chunk before it."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16_000)
        f.writeframes(b"\0\0" * int(16_000 * seconds))
    data = buf.getvalue()
    if not metadata_bytes:
        return data
    chunk = b"LIST" + struct.pack("<I", metadata_bytes) + b"\0" * metadata_bytes
    data = data[:36] + chunk + data[36:]
    return data[:4] + struct.pack("<I", len(data) - 8) + data[8:]


def test_wav_duration_falls_back_to_the_size(tmp_path):
    path = tmp_path / "audio.wav"
    path.write_bytes(b"not a wav")
    with patch("sentry_sdk.capture_exception") as capture_exception:
        assert wav_duration_seconds(str(path), 44 + 32_000 * 90) == 90
    assert capture_exception.called


def test_api_asr_records_and_charges_audio_seconds(asr_tts_pricing, user):
    page, sr = make_page(AsrPage, user, {"selected_model": "intron"})
    assert asr_run(sr, "intron", 600, **INTRON) == "hi"
    [cost] = UsageCost.objects.filter(saved_run=sr)
    assert cost.pricing.model_id == "intron-voice"
    assert cost.pricing.sku == ModelSku.asr_audio_seconds
    # 10 minutes at $0.17
    assert float(cost.dollar_amount) == pytest.approx(1.70)
    assert page.get_price_roundoff(sr.state) == 170


def test_asr_billing_does_not_use_the_display_pricing_link(asr_tts_pricing, user):
    AIModelSpec.objects.filter(name="intron").update(pricing=None)
    _, sr = make_page(AsrPage, user)
    asr_run(sr, "intron", 90, **INTRON)
    [cost] = UsageCost.objects.filter(saved_run=sr)
    assert cost.pricing.model_id == "intron-voice"


def test_modal_asr_records_gpu_time(asr_tts_pricing, user):
    _, sr = make_page(AsrPage, user)
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
def test_asr_without_a_minute_price_records_nothing(
    asr_tts_pricing, user, selected_model, patches, reported
):
    _, sr = make_page(AsrPage, user)
    with patch("sentry_sdk.capture_message") as capture_message:
        assert asr_run(sr, selected_model, 90, **patches) == "hi"
    assert not UsageCost.objects.filter(saved_run=sr).exists()
    assert capture_message.called == reported


def test_mansa_is_sent_the_ffprobe_duration(asr_tts_pricing, user):
    _, sr = make_page(AsrPage, user)
    mansa = MagicMock()
    mansa.return_value.json.return_value = {"data": {"transcript": "hi"}}
    # 6 seconds of audio and 1 MB of metadata
    audio = MagicMock(content=b"\0" * (32_000 * 6 + 1_000_000), status_code=200)
    with patch("daras_ai_v2.asr.requests.get", return_value=audio):
        assert asr_run(sr, "mansa", 6, "en", _call_mansa_transcribe=mansa) == "hi"
    assert mansa.call_args.kwargs["json"]["durationSeconds"] == 6


def test_asr_model_is_found_among_asr_models_only(asr_tts_pricing):
    AIModelSpec.objects.filter(name="intron").update(
        category=AIModelSpec.Categories.audio
    )
    assert get_asr_model(AsrModels.intron) is None


# TTS


@pytest.mark.parametrize(
    "provider, state, expected",
    [
        (TextToSpeechProviders.OPEN_AI, {}, dict(model_id="tts-1")),
        (
            TextToSpeechProviders.OPEN_AI,
            {"openai_tts_model": "gpt_4_o_mini"},
            dict(model_id="gpt-4o-mini-tts"),
        ),
        (TextToSpeechProviders.GEMINI_TTS, {}, dict(model_id="gemini-3.8-flash-tts")),
        (TextToSpeechProviders.SARVAM, {}, dict(name="bulbul_v3")),
        (TextToSpeechProviders.INTRON, {}, dict(name="sahara_v2_5")),
        # no pricing row: no published price
        (TextToSpeechProviders.GHANA_NLP, {}, dict(name="ghana_nlp_tts")),
        (GOOGLE, {}, dict(model_id="Neural2")),
        (GOOGLE, {"google_voice_name": "en-IN-Chirp3-HD-Aoede"}, dict(model_id="Chirp3-HD")),
        (GOOGLE, {"google_voice_name": "cmn-CN-Wavenet-A"}, dict(model_id="Wavenet")),
        (GOOGLE, {"google_voice_name": "en-US-Journey-D"}, dict(model_id="Chirp3-HD")),
        # the run strips the voice name, and so does its price
        (GOOGLE, {"google_voice_name": " en-US-Studio-O "}, dict(model_id="Studio")),
        # a type with no price of its own: the run keeps the flat price
        (GOOGLE, {"google_voice_name": "en-US-News-K"}, None),
        # a type name that is not the third part does not count
        (GOOGLE, {"google_voice_name": "en-US-Casual-Studio"}, None),
    ],
)  # fmt: skip
def test_tts_model_lookup(provider, state, expected):
    assert tts_model_lookup(provider, state) == expected


@pytest.mark.parametrize(
    "voice, model_id",
    [("en-US-Ava:DragonHDLatestNeural", "neural-hd"), ("en-US-JennyNeural", "neural")],
)
def test_azure_hd_voices_have_their_own_price(voice, model_id):
    with patch(
        "recipes.TextToSpeech.azure_tts_voices",
        return_value={"v": {"ShortName": voice}},
    ):
        lookup = tts_model_lookup(
            TextToSpeechProviders.AZURE_TTS, {"azure_voice_name": "v"}
        )
    assert lookup == dict(model_id=model_id)


@pytest.mark.parametrize(
    "provider, state, expected",
    [
        (GOOGLE, {"google_voice_name": "en-US-Studio-O"}, "google_tts_studio"),
        (TextToSpeechProviders.SARVAM, {}, "bulbul_v3"),
        (TextToSpeechProviders.ELEVEN_LABS, {}, None),
    ],
)
def test_get_tts_model(asr_tts_pricing, provider, state, expected):
    tts_model = get_tts_model(provider, state)
    assert (tts_model and tts_model.name) == expected


def test_tts_run_records_and_is_charged_its_characters(asr_tts_pricing, user):
    state = {
        "tts_provider": "GOOGLE_TTS",
        "google_voice_name": "en-US-Studio-O",
        "text_prompt": "x" * 100_000,
    }
    page, sr = make_page(TextToSpeechPage, user, state)
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


@pytest.mark.parametrize(
    "state, expected",
    [
        # 0.079 credits a character
        ({"tts_provider": "ELEVEN_LABS", "text_prompt": "x" * 1000}, 79),
        # no published price
        ({"tts_provider": "GHANA_NLP", "text_prompt": "hello"}, TextToSpeechPage.price),
    ],
)
def test_tts_without_recorded_usage_keeps_its_old_price(
    asr_tts_pricing, user, state, expected
):
    page, _ = make_page(TextToSpeechPage, user, state)
    assert page.get_price_roundoff(state) == expected


def test_charge_rounds_away_float_noise(asr_tts_pricing, user):
    page, _ = make_page(TextToSpeechPage, user)
    with patch.object(TextToSpeechPage, "get_raw_price", return_value=3.0000000001):
        assert page.get_price_roundoff({}) == 3


# Agent


def test_agent_notes_list_speech_costs_apart_from_the_llm(asr_tts_pricing, user):
    page, sr = make_page(VideoBotsPage, user, {"tts_provider": "GOOGLE_TTS"})
    with patch("celeryapp.tasks.get_running_saved_run", return_value=sr):
        record_cost_auto("chirp_3", ModelSku.asr_audio_seconds, 600)
        record_cost_auto("Studio", ModelSku.tts_characters, 100_000)
    # 10 minutes at $0.016, and 100K characters at $160 / 1M
    expected = {"Chirp 3": 16, "Google Studio": 1600}
    assert page.get_speech_credits() == pytest.approx(expected)
    set_session_state({"selected_model": "gpt_4_o"})
    parts = dict(page.get_cost_parts())
    assert {name: parts[name] for name in expected} == expected


@pytest.mark.parametrize(
    "api_key, asr_seconds, expected",
    [
        # no usage recorded: 1 credit, 3 per run, 7.9 for 100 characters
        (None, 0, 1 + 3 + 7.9),
        # the user's own ElevenLabs key: no TTS charge
        ("my-key", 0, 1 + 3),
        # 10 minutes of Chirp 3 recorded: 16 credits, as a Decimal
        (None, 600, 16 + 3 + 7.9),
    ],
)
def test_elevenlabs_agent_pays_its_tts_by_characters(
    asr_tts_pricing, user, api_key, asr_seconds, expected
):
    state = {
        "tts_provider": "ELEVEN_LABS",
        "elevenlabs_api_key": api_key,
        "raw_tts_text": ["x" * 100],
    }
    page, sr = make_page(VideoBotsPage, user, state)
    if asr_seconds:
        with patch("celeryapp.tasks.get_running_saved_run", return_value=sr):
            record_cost_auto("chirp_3", ModelSku.asr_audio_seconds, asr_seconds)
    assert float(page.get_raw_price(state)) == pytest.approx(expected)


@pytest.mark.parametrize(
    "costs, expected",
    [
        # three costs under a credit round to one credit in all, not three
        (
            {"LLM": 0.13, "ASR": 0.06, "TTS": 0.09},
            [("LLM", 1), ("ASR", 0.06), ("TTS", 0.09)],
        ),
        # the leftover credits go to the largest fractions
        ({"LLM": 2.4, "ASR": 0.7, "TTS": 1.6}, [("LLM", 2), ("ASR", 1), ("TTS", 2)]),
        # float noise does not round up a whole total
        ({"LLM": 2.0000000001, "ASR": 1.0}, [("LLM", 2), ("ASR", 1)]),
    ],
)
def test_split_rounded_credits_add_up_to_the_rounded_total(costs, expected):
    assert split_rounded_credits(costs) == expected


def test_a_part_under_a_credit_shows_as_less_than_a_cent():
    assert format_credits_as_dollars(0.06) == "<$0.01"
    assert format_credits_as_dollars(3) == "$0.03"


def make_page(page_cls, user, state=None):
    """A saved run of the page's workflow, and the page that shows it."""
    sr = SavedRun.objects.create(
        workflow=page_cls.workflow, run_id="run", uid=user.uid, state=state or {}
    )
    page = page_cls(user=user, query_params=dict(run_id=sr.run_id, uid=user.uid))
    return page, sr


def asr_run(sr, selected_model: str, seconds: float, language=None, **patches):
    """Run ASR on a wav of `seconds`, with the provider calls in `patches`
    mocked, as the running saved run `sr`."""
    wav = ("gs://bucket/audio.wav", 44 + int(32_000 * seconds))
    probe = {"streams": [{"duration": str(seconds)}]}
    with (
        patch("celeryapp.tasks.get_running_saved_run", return_value=sr),
        patch("daras_ai_v2.asr.audio_url_to_wav_url", return_value=wav),
        patch("daras_ai_v2.asr.ffprobe", return_value=probe),
        patch.multiple("daras_ai_v2.asr", **patches) if patches else nullcontext(),
    ):
        return run_asr("https://example.com/a.mp3", selected_model, language=language)
