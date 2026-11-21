import io

from PIL import Image

from photoscan import assettag, decide, privacy
from photoscan.model import Box, Crop, Line, Person, Word
from conftest import analysis


def L(text, conf=0.99):
    return Line(text, [Word(w, conf) for w in text.split()])


def test_clean_tag():
    t = assettag.find_tags([L("CONTOSO PORTO"), L("CON-48213", 0.97)])
    assert len(t) == 1 and t[0].tag == "CON-48213" and t[0].confidence == 0.97 and not t[0].corrected
    assert assettag.usable(t[0])


def test_tag_with_space_or_lowercase_noise_variants():
    assert assettag.find_tags([L("CON 48213")])[0].tag == "CON-48213"
    assert assettag.find_tags([L("CON-48213X")]) == []            # not a whole token: never guess


def test_lookalike_letters_are_corrected_and_flagged():
    t = assettag.find_tags([L("CON-4821O")])[0]
    assert t.tag == "CON-48210" and t.corrected and not assettag.usable(t)
    t2 = assettag.find_tags([L("CON-I2345")])[0]
    assert t2.tag == "CON-12345" and t2.corrected


def test_letters_that_do_not_become_digits_are_not_a_tag():
    assert assettag.find_tags([L("CON-ABCDE")]) == []


def test_low_confidence_is_not_usable():
    t = assettag.find_tags([Line("CON-48213", [Word("CON-48213", 0.55)])])[0]
    assert t.confidence == 0.55 and not assettag.usable(t)


def test_duplicate_tag_keeps_best_confidence():
    t = assettag.find_tags([L("CON-48213", 0.6), L("CON-48213", 0.9)])
    assert len(t) == 1 and t[0].confidence == 0.9


# ---- privacy -------------------------------------------------------------------------------------------------
def noisy(w=300, h=200):
    im = Image.new("RGB", (w, h))
    px = im.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def test_people_are_pixelated_and_others_untouched():
    src = noisy()
    red = privacy.redact_people(src, [Person(Box(50, 40, 100, 120), 0.9)])
    assert len(red.blurred) == 1 and red.ignored == 0
    assert privacy.region_changed(src, red.data, red.blurred[0])
    assert not privacy.region_changed(src, red.data, Box(200, 0, 90, 30))       # far corner is identical


def test_low_confidence_person_is_blurred_at_the_default_threshold():
    # Learn's own people example returns a visible person at 0.27: the default threshold must not drop it
    red = privacy.redact_people(noisy(), [Person(Box(10, 10, 80, 80), 0.27)])
    assert len(red.blurred) == 1


def test_below_threshold_is_counted_not_silently_dropped():
    red = privacy.redact_people(noisy(), [Person(Box(10, 10, 80, 80), 0.10)])
    assert red.blurred == [] and red.ignored == 1


def test_box_outside_the_image_is_clamped():
    red = privacy.redact_people(noisy(), [Person(Box(250, 150, 200, 200), 0.9)])
    b = red.blurred[0]
    assert b.x + b.w <= 300 and b.y + b.h <= 200


def test_pixelation_is_not_reversible_by_resizing_back():
    src = noisy()
    red = privacy.redact_people(src, [Person(Box(0, 0, 120, 120), 0.9)])
    a = Image.open(io.BytesIO(src)).convert("RGB").crop((0, 0, 120, 120))
    b = Image.open(io.BytesIO(red.data)).convert("RGB").crop((0, 0, 120, 120))
    assert len(set(b.tobytes()[i:i + 3] for i in range(0, len(b.tobytes()), 3))) < len(set(a.tobytes()[i:i + 3] for i in range(0, len(a.tobytes()), 3))) / 10     # far fewer distinct pixels: blocks


def test_thumbnail_comes_from_the_given_image_and_respects_the_crop():
    t = privacy.thumbnail(noisy(), Crop(1.0, Box(0, 0, 200, 200)), size=64)
    im = Image.open(io.BytesIO(t))
    assert im.size == (64, 64)


# ---- decisions -----------------------------------------------------------------------------------------------
def test_decisions():
    ok = assettag.find_tags([L("CON-48213", 0.97)])
    assert decide.decide(analysis(), ok)[0] == "attach-to-asset"
    assert decide.decide(analysis(), [])[0] == "manual-review"
    assert decide.decide(analysis(), assettag.find_tags([L("CON-4821O")]))[0] == "confirm-tag"
    assert decide.decide(analysis(), assettag.find_tags([L("CON-48213", 0.4)]))[0] == "manual-review"
    two = assettag.find_tags([L("CON-48213"), L("CON-11111")])
    d, why = decide.decide(analysis(), two)
    assert d == "manual-review" and "2 different" in why[0]
    assert decide.decide(None, [], "boom") == ("manual-review", ["boom"])


def test_text_in_a_photo_with_people_adds_a_warning():
    a = analysis(lines=[("CON-48213", 0.97)], people=[((0, 0, 10, 10), 0.9)])
    d, why = decide.decide(a, assettag.find_tags(a.lines))
    assert d == "attach-then-review" and "names on badges or screens are not blurred" in why[0]
