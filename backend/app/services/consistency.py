"""Character consistency check.

Without a GPU-heavy identity model, the engine uses an honest, cheap signal:
colour-palette similarity (HSV hue/saturation histogram correlation) between a
character's reference image and each scene image. A low score flags the scene
for review/regeneration in the Scene Manager. It does not prove identity; it
catches the common failure (wrong fur colour / different-looking animal).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

THRESHOLD = 0.35


def _hist(img: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # ignore very dark / very bright / unsaturated pixels (background, sky, shadows)
    mask = ((hsv[..., 1] > 40) & (hsv[..., 2] > 40) & (hsv[..., 2] < 245)).astype(np.uint8) * 255
    h = cv2.calcHist([hsv], [0, 1], mask, [30, 16], [0, 180, 0, 256])
    cv2.normalize(h, h)
    return h


def reference_crop(img: np.ndarray) -> np.ndarray:
    """Character sheets are centred; use the middle region."""
    h, w = img.shape[:2]
    return img[int(h * 0.15): int(h * 0.85), int(w * 0.2): int(w * 0.8)]


def _windows(img: np.ndarray):
    """Overlapping half-size windows: the character usually fills only part of a scene."""
    h, w = img.shape[:2]
    wh, ww = h // 2, w // 2
    for y in (0, h // 4, h // 2):
        for x in (0, w // 4, w // 2):
            yield img[y:y + wh, x:x + ww]
    yield img


def similarity(reference: Path, scene: Path) -> float:
    ref, sc = cv2.imread(str(reference)), cv2.imread(str(scene))
    if ref is None or sc is None:
        return 0.0
    rh = _hist(reference_crop(ref))
    best = max(cv2.compareHist(rh, _hist(win), cv2.HISTCMP_CORREL) for win in _windows(sc))
    return float(max(0.0, best))


def check(reference: Path | None, scene: Path) -> tuple[float | None, bool]:
    if not reference or not reference.exists():
        return None, False
    score = round(similarity(reference, scene), 3)
    return score, score < THRESHOLD
