"""Reference media analyzer.

Measures style signals from a reference video/image the USER UPLOADS
(legally accessible material): pacing (cuts per minute), brightness,
saturation, warmth, dominant colours and motion intensity. These numbers
become style notes for the storyboard; no frames are copied into the output.

Reference URLs are stored but NOT downloaded: platforms such as YouTube do not
permit downloading through their terms. Upload a file to have it analysed.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _palette(img: np.ndarray, k: int = 4) -> list[str]:
    small = cv2.resize(img, (64, 64)).reshape(-1, 3).astype(np.float32)
    _, labels, centers = cv2.kmeans(small, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0), 3, cv2.KMEANS_PP_CENTERS)
    order = np.argsort(-np.bincount(labels.flatten(), minlength=k))
    return ["#%02x%02x%02x" % tuple(int(c) for c in centers[i][::-1]) for i in order]


def analyze(path: Path) -> dict:
    img = cv2.imread(str(path))
    if img is not None:  # still image
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        return {"type": "image", "brightness": float(hsv[..., 2].mean() / 255), "saturation": float(hsv[..., 1].mean() / 255),
                "warmth": float((img[..., 2].mean() - img[..., 0].mean()) / 255), "palette": _palette(img)}

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("unsupported reference file")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(fps / 4))  # sample 4 frames per second
    prev_hist, prev_gray = None, None
    cuts, motion, bright, sat, warm, frames = 0, [], [], [], [], []
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, f = cap.retrieve()
            if not ok:
                break
            f = cv2.resize(f, (320, int(320 * f.shape[0] / f.shape[1])))
            hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
            cv2.normalize(hist, hist)
            gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            if prev_hist is not None:
                if cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL) < 0.6:
                    cuts += 1
                else:
                    motion.append(float(np.mean(cv2.absdiff(gray, prev_gray)) / 255))
            prev_hist, prev_gray = hist, gray
            bright.append(hsv[..., 2].mean() / 255)
            sat.append(hsv[..., 1].mean() / 255)
            warm.append((f[..., 2].mean() - f[..., 0].mean()) / 255)
            if len(frames) < 12 and idx % (step * 8) == 0:
                frames.append(f)
        idx += 1
    cap.release()
    duration = (total or idx) / fps
    palette = _palette(np.concatenate(frames, axis=0)) if frames else []
    return {
        "type": "video", "duration_s": round(duration, 1), "cuts": cuts,
        "cuts_per_minute": round(cuts / max(duration / 60, 1e-6), 1),
        "avg_shot_s": round(duration / (cuts + 1), 1),
        "motion": round(float(np.mean(motion)) if motion else 0.0, 3),
        "brightness": round(float(np.mean(bright)) if bright else 0, 3),
        "saturation": round(float(np.mean(sat)) if sat else 0, 3),
        "warmth": round(float(np.mean(warm)) if warm else 0, 3),
        "palette": palette,
    }


def to_style_notes(a: dict) -> str:
    notes = []
    if a.get("type") == "video":
        if a["cuts"] == 0:
            notes.append(f"single continuous shot ({a['duration_s']} s)")
        else:
            pace = "fast-paced editing" if a["avg_shot_s"] < 2.5 else "moderate pacing" if a["avg_shot_s"] < 6 else "slow, lingering shots"
            notes.append(f"{pace} (average shot {a['avg_shot_s']} s)")
        notes.append("energetic camera/subject motion" if a["motion"] > 0.06 else "calm, smooth motion")
    b = a.get("brightness", 0.5)
    notes.append("bright, high-key lighting" if b > 0.6 else "dark, low-key lighting" if b < 0.35 else "balanced lighting")
    s = a.get("saturation", 0.4)
    notes.append("vivid saturated colours" if s > 0.5 else "muted desaturated colours" if s < 0.25 else "natural colour")
    w = a.get("warmth", 0)
    notes.append("warm golden tones" if w > 0.05 else "cool blue tones" if w < -0.05 else "neutral colour temperature")
    if a.get("palette"):
        notes.append("palette " + " ".join(a["palette"]))
    return "; ".join(notes)
