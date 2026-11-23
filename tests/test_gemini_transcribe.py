from unittest import mock

from daras_ai_v2 import asr, settings


def test_gemini_transcribe_sends_config_and_reads_segments(monkeypatch):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", "bucket")
    monkeypatch.setattr(settings, "GS_MEDIA_PATH", "daras_ai/media")
    response = mock.Mock(ok=True, status_code=200)
    response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "hello there",
                            "audioTranscription": {
                                "startOffset": "0.500s",
                                "endOffset": "1.250s",
                            },
                        },
                        {"audioTranscription": {"text": "general kenobi"}},
                        {"text": ""},
                    ]
                }
            }
        ]
    }
    session = mock.Mock()
    session.post.return_value = response
    monkeypatch.setattr(asr, "get_google_auth_session", lambda: (session, "proj"))

    ret = asr.gemini_transcribe_asr(
        "https://storage.googleapis.com/bucket/daras_ai/media/x/audio.wav",
        model_id="gemini-3.5-transcribe",
        language="en",
        word_timestamps=True,
    )

    url = session.post.call_args.args[0]
    body = session.post.call_args.kwargs["json"]
    assert url.endswith(
        "/projects/proj/locations/global/publishers/google/models/gemini-3.5-transcribe:generateContent"
    )
    assert body["contents"][0]["parts"][0]["fileData"] == {
        "fileUri": "gs://bucket/daras_ai/media/x/audio.wav",
        "mimeType": "audio/wav",
    }
    assert body["generationConfig"]["audioTranscriptionConfig"] == {
        "wordTimestamp": True,
        "languageCodes": ["en-US"],
    }
    assert ret["text"] == "hello there general kenobi"
    assert ret["chunks"][0]["timestamp"] == (0.5, 1.25)
    assert ret["chunks"][1]["timestamp"] == (0.0, 0.0)
