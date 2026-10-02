import tempfile
import typing

from daras_ai_v2.exceptions import ffmpeg, ffprobe

# shrink anything bigger than about a megapixel, keeping the aspect ratio
DEFAULT_IMAGE_RESIZE = f"{1024**2}@>"


def resize_and_convert_image(
    data: bytes,
    *,
    keep_formats: typing.Container[str],
    resize: str = DEFAULT_IMAGE_RESIZE,
) -> tuple[bytes, bool]:
    """
    Shrink an image to the `resize` geometry, converting it to png unless its format
    (as imagemagick names it, lowercased) is in `keep_formats`.

    Returns the new bytes, and whether the image was converted to png.
    """
    from wand.image import Image

    with Image(blob=data) as img:
        converted = img.format.lower() not in keep_formats
        if converted:
            img.format = "png"
        img.transform(resize=resize)
        return img.make_blob(), converted


def video_codec_name(data: bytes) -> str | None:
    """The codec of the first video stream, as ffprobe names it, e.g. "h264"."""
    with tempfile.NamedTemporaryFile() as infile:
        infile.write(data)
        infile.flush()
        streams = ffprobe(infile.name)["streams"]
    return next(
        (s.get("codec_name") for s in streams if s.get("codec_type") == "video"), None
    )


def video_bytes_to_mp4(data: bytes) -> bytes:
    """Re-encode any video ffmpeg can read as an h264 + aac mp4."""
    with (
        tempfile.NamedTemporaryFile() as infile,
        tempfile.NamedTemporaryFile(suffix=".mp4") as outfile,
    ):
        infile.write(data)
        infile.flush()
        ffmpeg(
            "-i", infile.name,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            # yuv420p needs even dimensions
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:a", "aac",
            "-movflags", "+faststart",
            outfile.name,
        )  # fmt:skip
        return outfile.read()
