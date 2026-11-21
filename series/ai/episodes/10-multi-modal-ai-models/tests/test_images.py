import base64
import io

import pytest
from PIL import Image

from mmticket import images
from mmticket.images import ImageError, content_parts, has_metadata, prepare_image


def jpeg_with_exif(orientation=1, size=(300, 200)):
    im = Image.new("RGB", size, (200, 30, 30))
    ex = Image.Exif()
    ex[0x0112] = orientation                  # Orientation
    ex[0x010F] = "FictionalCam"               # Make
    gps = ex.get_ifd(0x8825)
    gps[1], gps[2] = "N", (41.0, 9.0, 0.0)    # GPS latitude ref + value
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=ex)
    return buf.getvalue()


def decode(url):
    head, b64 = url.split(",", 1)
    return head, base64.b64decode(b64)


def test_exif_and_gps_are_dropped_and_reported():
    raw = jpeg_with_exif()
    assert has_metadata(raw)
    p = prepare_image(raw, "photo.jpg")
    head, data = decode(p.data_url)
    assert head == "data:image/png;base64" and p.metadata_removed
    assert not has_metadata(data) and b"FictionalCam" not in data and b"Exif" not in data


def test_camera_rotation_is_applied_before_metadata_is_dropped():
    p = prepare_image(jpeg_with_exif(orientation=6), "rot.jpg")        # 6 = rotate 90 degrees
    assert (p.width, p.height) == (200, 300)


def test_large_screenshot_is_downscaled_and_says_so():
    buf = io.BytesIO()
    Image.new("RGB", (4000, 1000), "white").save(buf, "PNG")
    p = prepare_image(buf.getvalue(), "wide.png", max_side=2048)
    assert (p.width, p.height) == (2048, 512) and any("downscaled" in n for n in p.notes)


def test_animated_gif_is_flagged_as_first_frame_only():
    frames = [Image.new("RGB", (50, 50), c) for c in ("red", "blue")]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
    p = prepare_image(buf.getvalue(), "a.gif")
    assert any("first frame" in n for n in p.notes)


def test_unsupported_format_is_refused_with_the_allowed_list():
    buf = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buf, "BMP")
    with pytest.raises(ImageError, match="BMP.*JPEG, PNG, GIF, or WEBP"):
        prepare_image(buf.getvalue(), "x.bmp")


def test_not_an_image_and_over_20_mb_are_refused_before_decoding():
    with pytest.raises(ImageError, match="not a readable image"):
        prepare_image(b"hello", "x.png")
    with pytest.raises(ImageError, match="over the 20 MB"):
        prepare_image(b"\0" * (images.MAX_IMAGE_BYTES + 1), "big.png")


def test_content_parts_use_data_urls_with_the_requested_detail_and_cap_at_ten():
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), "white").save(buf, "PNG")
    p = prepare_image(buf.getvalue(), "w.png")
    parts = content_parts([p], "low")
    assert parts == [{"type": "image_url", "image_url": {"url": p.data_url, "detail": "low"}}]
    assert p.data_url.startswith("data:") and "http" not in p.data_url[:10]      # private data never as a public URL
    with pytest.raises(ImageError, match="limit is 10"):
        content_parts([p] * 11, "high")
    with pytest.raises(ImageError, match="detail must be"):
        content_parts([p], "ultra")
    with pytest.raises(ImageError, match="no image"):
        content_parts([], "low")
