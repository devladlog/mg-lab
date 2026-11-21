"""The only module that imports the Azure SDK. Keyless: Entra ID against the resource's custom subdomain."""
from __future__ import annotations

import os

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures

from .limits import check_ratios
from .model import Analysis, Box, Crop, Line, Person, Word

FEATURES = [VisualFeatures.CAPTION, VisualFeatures.TAGS, VisualFeatures.OBJECTS,
            VisualFeatures.READ, VisualFeatures.PEOPLE, VisualFeatures.SMART_CROPS]
DEFAULT_RATIOS = [1.0, 1.78]      # square (ticket list) and 16:9 (ticket header)


def make_client(endpoint: str | None = None, credential=None, **kw) -> ImageAnalysisClient:
    endpoint = endpoint or os.environ.get("PHOTOSCAN_ENDPOINT")
    if not endpoint:
        raise SystemExit("Set PHOTOSCAN_ENDPOINT (the vision resource endpoint) or pass --endpoint.")
    if credential is None:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
    return ImageAnalysisClient(endpoint=endpoint, credential=credential, **kw)


def _box(b) -> Box:
    return Box(b.x, b.y, b.width, b.height)


class AzureVisionBackend:
    def __init__(self, client: ImageAnalysisClient, ratios: list[float] | None = None):
        self.client = client
        self.ratios = check_ratios(list(ratios or DEFAULT_RATIOS))
        self.calls = 0

    def analyze(self, image: bytes) -> Analysis:
        self.calls += 1
        r = self.client.analyze(image_data=image, visual_features=FEATURES, smart_crops_aspect_ratios=self.ratios,
                                gender_neutral_caption=True, language="en")
        a = Analysis(r.metadata.width, r.metadata.height, r.model_version)
        if r.caption is not None:
            a.caption, a.caption_confidence = r.caption.text, r.caption.confidence
        if r.tags is not None:
            a.tags = [(t.name, t.confidence) for t in r.tags.list]
        if r.objects is not None:
            a.objects = [(o.tags[0].name, o.tags[0].confidence, _box(o.bounding_box)) for o in r.objects.list if o.tags]
        if r.read is not None:
            a.lines = [Line(ln.text, [Word(w.text, w.confidence) for w in ln.words]) for b in r.read.blocks for ln in b.lines]
        if r.people is not None:
            a.people = [Person(_box(p.bounding_box), p.confidence) for p in r.people.list]
        if r.smart_crops is not None:
            a.crops = [Crop(c.aspect_ratio, _box(c.bounding_box)) for c in r.smart_crops.list]
        return a
