from unittest.mock import Mock, patch

import pytest

from daras_ai_v2 import fal_ai

STEM = "2026-09-24 12-41-10 UTC - Birds - In Vitrine v5.4"


@pytest.fixture
def uploaded_filenames():
    with (
        patch.object(fal_ai.requests, "get", return_value=Mock(content=b"x")),
        patch.object(fal_ai, "raise_for_status"),
        patch.object(fal_ai, "get_mimetype_from_response", return_value="video/mp4"),
        patch.object(
            fal_ai,
            "upload_file_from_bytes",
            side_effect=lambda filename, *args, **kwargs: filename,
        ),
    ):
        yield


def test_single_asset_takes_the_stem(uploaded_filenames):
    out = fal_ai._rewrite_fal_asset_urls(
        {"video": {"url": "https://v3b.fal.media/files/b/x/rOXy_minimax-h3.mp4"}},
        filename_stem=STEM,
    )

    assert out == {"video": {"url": f"{STEM}.mp4"}}


def test_single_item_list_is_not_numbered(uploaded_filenames):
    out = fal_ai._rewrite_fal_asset_urls(
        {"images": [{"url": "https://v3b.fal.media/files/b/x/a.png"}]},
        filename_stem=STEM,
    )

    assert out == {"images": [{"url": f"{STEM}.png"}]}


def test_multiple_assets_are_numbered(uploaded_filenames):
    out = fal_ai._rewrite_fal_asset_urls(
        {
            "images": [
                {"url": "https://v3b.fal.media/files/b/x/a.png"},
                {"url": "https://v3b.fal.media/files/b/x/b.png"},
                {"url": "https://v3b.fal.media/files/b/x/c.png"},
            ]
        },
        filename_stem=STEM,
    )

    assert [image["url"] for image in out["images"]] == [
        f"{STEM} - 1.png",
        f"{STEM} - 2.png",
        f"{STEM} - 3.png",
    ]


def test_without_a_stem_keeps_fal_names(uploaded_filenames):
    out = fal_ai._rewrite_fal_asset_urls(
        [
            {"url": "https://v3b.fal.media/files/b/x/a.png"},
            {"url": "https://v3b.fal.media/files/b/x/b.png"},
        ]
    )

    assert out == [{"url": "a.png"}, {"url": "b.png"}]


@pytest.mark.parametrize(
    "fal_name, stem, expected",
    [
        ("rOXy", STEM, f"{STEM}.mp4"),
        ("rOXy_minimax-h3.mp4", STEM, f"{STEM}.mp4"),
        ("rOXy", None, "rOXy.mp4"),
        ("rOXy_minimax-h3.mp4", None, "rOXy_minimax-h3.mp4"),
    ],
)
def test_extension_survives_a_dotted_stem(fal_name, stem, expected, uploaded_filenames):
    url = f"https://v3b.fal.media/files/b/x/{fal_name}"

    assert fal_ai._rewrite_fal_asset_urls(url, filename_stem=stem) == expected
