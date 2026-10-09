import shutil

import pytest

from daras_ai_v2.embedding_model import _convert_for_gemini
from daras_ai_v2.exceptions import ffmpeg
from daras_ai_v2.media_conversion import (
    resize_and_convert_image,
    video_codec_name,
)

# these shell out to ffmpeg and imagemagick, which the docker image has but CI doesn't
wand_image = pytest.importorskip("wand.image")
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")

PNG_MAGIC = b"\x89PNG"


def make_image(fmt: str, frames: int = 1) -> bytes:
    from wand.color import Color

    with wand_image.Image() as img:
        for i in range(frames):
            with wand_image.Image(
                width=16, height=16, background=Color("red" if i % 2 else "blue")
            ) as frame:
                img.sequence.append(frame)
        img.format = fmt
        return img.make_blob()


def make_with_ffmpeg(tmp_path, name: str, *args: str) -> bytes:
    out = tmp_path / name
    ffmpeg(*args, str(out))
    return out.read_bytes()


def test_gif_is_converted_to_png():
    data, mime_type = _convert_for_gemini("u", make_image("gif"), "image/gif")
    assert (mime_type, data[:4]) == ("image/png", PNG_MAGIC)


def test_animated_gif_is_converted_to_a_single_png():
    data, mime_type = _convert_for_gemini("u", make_image("gif", frames=3), "image/gif")
    assert (mime_type, data[:4]) == ("image/png", PNG_MAGIC)
    with wand_image.Image(blob=data) as img:
        assert len(img.sequence) == 1


def test_png_stays_png():
    data, mime_type = _convert_for_gemini("u", make_image("png"), "image/png")
    assert (mime_type, data[:4]) == ("image/png", PNG_MAGIC)


def test_image_type_gemini_doesnt_name_is_converted_even_if_the_format_is_fine():
    # a jpeg served as image/pjpeg: sending that type along would fail at vertex
    data, mime_type = _convert_for_gemini("u", make_image("jpeg"), "image/pjpeg")
    assert (mime_type, data[:4]) == ("image/png", PNG_MAGIC)


def test_ogg_audio_is_converted_to_wav(tmp_path):
    ogg = make_with_ffmpeg(
        tmp_path,
        "tone.ogg",
        "-f",
        "lavfi",
        "-i",
        "sine=duration=1",
        "-c:a",
        "libvorbis",
    )
    data, mime_type = _convert_for_gemini("u", ogg, "audio/ogg")
    assert (mime_type, data[:4]) == ("audio/wav", b"RIFF")


def test_webm_video_is_reencoded_as_h264_mp4(tmp_path):
    webm = make_with_ffmpeg(
        tmp_path,
        "clip.webm",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=63x45:rate=5",
        "-c:v", "libvpx",
    )  # fmt:skip
    data, mime_type = _convert_for_gemini("u", webm, "video/webm")
    assert (mime_type, video_codec_name(data)) == ("video/mp4", "h264")


def test_mp4_with_a_codec_gemini_cant_read_is_reencoded(tmp_path):
    # the container alone isn't enough: gemini only reads av1/h264/h265/vp9 inside it
    mp4 = make_with_ffmpeg(
        tmp_path,
        "clip.mp4",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=5",
        "-c:v", "mpeg4",
    )  # fmt:skip
    data, mime_type = _convert_for_gemini("u", mp4, "video/mp4")
    assert (mime_type, video_codec_name(data)) == ("video/mp4", "h264")


def test_h264_mp4_is_left_alone(tmp_path):
    mp4 = make_with_ffmpeg(
        tmp_path,
        "clip.mp4",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
    )  # fmt:skip
    assert _convert_for_gemini("u", mp4, "video/mp4") == (mp4, "video/mp4")


def test_file_uploads_still_keep_gifs():
    # moving the image code out of the upload endpoint mustn't change what it does
    from routers.root import UPLOAD_IMAGE_FORMATS

    gif = make_image("gif")
    _, converted = resize_and_convert_image(gif, keep_formats=UPLOAD_IMAGE_FORMATS)
    assert not converted
    _, converted = resize_and_convert_image(
        make_image("tiff"), keep_formats=UPLOAD_IMAGE_FORMATS
    )
    assert converted
