import io

import pytest
from PIL import Image

from conftest import ENDPOINT
from photoscan import limits, samples
from photoscan.azure_backend import DEFAULT_RATIOS, FEATURES
from photoscan.prepare import prepare
from photoscan.model import Analysis


def test_sdk_request_shape_and_entra_scope(sdk_backend, service, cred):
    raw = prepare(samples.generate()["label-clean"]).data
    sdk_backend.analyze(raw)
    req = service.requests[0]
    assert req["path"].endswith("/computervision/imageanalysis:analyze")
    assert req["query"]["api-version"] == ["2023-10-01"]
    assert {f.lower() for f in req["query"]["features"][0].split(",")} == {"caption", "tags", "objects", "read", "people", "smartcrops"}
    assert req["query"]["smartcrops-aspect-ratios"] == ["1.0,1.78"]
    assert req["query"]["gender-neutral-caption"] == ["true"]
    assert req["headers"]["Authorization"] == "Bearer fake-entra-token"
    assert {k.lower(): v for k, v in req["headers"].items()}["content-type"] == "application/octet-stream"
    assert req["body_len"] == len(raw)                      # the image bytes themselves, one image per call
    assert "https://cognitiveservices.azure.com/.default" in cred.scopes
    assert "Ocp-Apim-Subscription-Key" not in req["headers"]


def test_sdk_response_is_normalised(sdk_backend):
    a = sdk_backend.analyze(prepare(samples.generate()["label-clean"]).data)
    assert isinstance(a, Analysis)
    assert a.caption == "a laptop with a label" and a.caption_confidence == 0.71
    assert a.tags[0] == ("laptop", 0.98)
    assert a.lines[1].text == "CON-48213" and a.lines[1].words[0].confidence == 0.97
    assert a.people[0].box.w == 50 and a.people[0].confidence == 0.9
    assert [c.aspect_ratio for c in a.crops] == DEFAULT_RATIOS
    assert a.model_version == "2023-10-01"


def test_sdk_http_error_propagates(sdk_backend, service):
    service.reply = lambda *a: (400, {"error": {"code": "InvalidRequest", "message": "The provided image is not valid"}})
    from azure.core.exceptions import HttpResponseError
    with pytest.raises(HttpResponseError):
        sdk_backend.analyze(prepare(samples.generate()["label-clean"]).data)


def test_feature_list_matches_what_we_use():
    assert {f.name for f in FEATURES} == {"CAPTION", "TAGS", "OBJECTS", "READ", "PEOPLE", "SMART_CROPS"}


def test_crop_ratio_limits_from_learn():
    assert limits.check_ratios([0.75, 1.0, 1.8]) == [0.75, 1.0, 1.8]
    with pytest.raises(ValueError):
        limits.check_ratios([0.7])
    with pytest.raises(ValueError):
        limits.check_ratios([2.0])


def png_of(size):
    b = io.BytesIO()
    Image.new("RGB", size, (1, 2, 3)).save(b, "PNG")
    return b.getvalue()


def test_image_limits():
    assert limits.check_image(png_of((60, 60))).width == 60
    with pytest.raises(limits.ImageRejected, match="greater than 50"):
        limits.check_image(png_of((50, 400)))
    with pytest.raises(limits.ImageRejected, match="not a readable image"):
        limits.check_image(b"not an image")
    with pytest.raises(limits.ImageRejected, match="20 MB"):
        limits.check_image(b"x" * (20 * 1024 * 1024))
    b = io.BytesIO()
    Image.new("RGB", (80, 80)).save(b, "PPM")
    with pytest.raises(limits.ImageRejected, match="not in the supported list"):
        limits.check_image(b.getvalue())


def test_prepare_applies_rotation_and_drops_exif_gps():
    raw = samples.generate()["label-phone-rotated"]
    with Image.open(io.BytesIO(raw)) as im:
        assert im.size == (800, 1200)                       # stored sideways
        assert im.getexif().get(0x0112) == 6 and im.getexif().get_ifd(0x8825)
    p = prepare(raw, "rot")
    assert (p.width, p.height) == (1200, 800)               # upright
    assert p.had_metadata and "metadata removed" in p.notes
    with Image.open(io.BytesIO(p.data)) as im:
        assert not im.getexif() and not im.info.get("exif")
    assert b"ContosoPhone" not in p.data and b"Exif" not in p.data


def test_prepare_downscales_and_stays_under_6mb():
    p = prepare(png_of((3000, 2000)), "big", max_side=1000)
    assert max(p.width, p.height) == 1000 and any("downscaled" in n for n in p.notes)
    assert len(p.data) < limits.SDK_SAFE_BYTES


def test_prepare_refuses_what_the_service_would_refuse():
    with pytest.raises(limits.ImageRejected):
        prepare(b"junk")
