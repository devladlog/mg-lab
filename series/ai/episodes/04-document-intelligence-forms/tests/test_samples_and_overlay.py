from decimal import Decimal

import pytest
from PIL import Image

from fixtures import analyze_result, sample
from invoice_intake.overlay import AMBER, GREEN, draw_overlay, field_boxes
from invoice_intake.samples import SAMPLES, write_samples


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    return write_samples(tmp_path_factory.mktemp("samples"))


def test_samples_meet_the_input_requirements(rendered):
    assert len(rendered) == 6
    for p in rendered:
        with Image.open(p) as im:
            assert im.format == "PNG"
            assert 50 <= min(im.size) and max(im.size) <= 10_000  # Learn: 50x50 .. 10,000x10,000 px
        assert p.stat().st_size < 4 * 1024 * 1024  # Learn: 4 MB max on the free (F0) tier


def test_sample_data_is_built_to_hit_each_rule():
    by = {s.file[:2]: s for s in SAMPLES}
    assert by["01"].subtotal + by["01"].tax == by["01"].total
    assert by["02"].subtotal + by["02"].tax != by["02"].total  # printed total is wrong on purpose
    assert by["03"].customer_vat != by["01"].customer_vat
    assert (by["05"].vendor_vat, by["05"].invoice_id) == (by["01"].vendor_vat, by["01"].invoice_id)
    assert by["04"].faded and by["01"].tax == Decimal("107.87")


def test_overlay_colours_boxes_by_threshold(rendered, tmp_path):
    image = next(p for p in rendered if p.name.startswith("04"))
    result = analyze_result(sample("04"), conf=0.95, overrides={"InvoiceTotal": 0.62})
    out = draw_overlay(image, result, tmp_path / "overlay.png")
    with Image.open(out) as im:
        px = im.convert("RGB")
        # InvoiceTotal box (x 980-1150, y 912-942) is amber, VendorName box (x 90-690, y 90-140) is green
        assert px.getpixel((1000, 912)) == AMBER
        assert px.getpixel((300, 140)) == GREEN


def test_pdf_polygons_in_inches_are_refused():
    result = analyze_result(sample("01"))
    result["pages"][0]["unit"] = "inch"
    with pytest.raises(ValueError, match="inches"):
        field_boxes(result)
