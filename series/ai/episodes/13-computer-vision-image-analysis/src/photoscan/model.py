"""What the rest of the code sees. Azure's types stop at azure_backend.py, so a replacement backend is one file
(Learn: Image Analysis is deprecated and retires on 25 September 2028)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int


@dataclass
class Word:
    text: str
    confidence: float


@dataclass
class Line:
    text: str
    words: list[Word]


@dataclass
class Person:
    box: Box
    confidence: float


@dataclass
class Crop:
    aspect_ratio: float
    box: Box


@dataclass
class Analysis:
    width: int
    height: int
    model_version: str = ""
    caption: str | None = None
    caption_confidence: float | None = None
    tags: list[tuple[str, float]] = field(default_factory=list)
    objects: list[tuple[str, float, Box]] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    crops: list[Crop] = field(default_factory=list)


class VisionBackend(Protocol):
    def analyze(self, image: bytes) -> Analysis: ...
