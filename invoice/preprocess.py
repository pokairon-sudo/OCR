"""Image → model-ready PNG.

Steps:
  1. Auto-crop to the receipt (bright rectangle against darker background).
  2. Upscale to a target width so small Persian digits are legible.
  3. Adaptive binarization to force clean black-on-white.

Every step falls back gracefully if it fails.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

import cv2
import numpy as np


def _auto_crop(gray: np.ndarray) -> np.ndarray:
    """Return the largest bright rectangular region, or the full image."""
    h, w = gray.shape[:2]
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(
        bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return gray
    largest = max(contours, key=cv2.contourArea)
    x, y, cw, ch = cv2.boundingRect(largest)
    if cw * ch < 0.25 * w * h:
        return gray  # detector probably grabbed glare, not the receipt
    pad = 12
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(w, x + cw + pad)
    y1 = min(h, y + ch + pad)
    return gray[y0:y1, x0:x1]


def preprocess(
    image_path: str,
    target_width: int = 1400,
    out_path: Optional[str] = None,
) -> str:
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"cv2 could not decode {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    crop = _auto_crop(gray)

    scale = target_width / crop.shape[1]
    if scale > 1.01:
        crop = cv2.resize(
            crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
    elif scale < 0.99:
        crop = cv2.resize(
            crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
        )

    binary = cv2.adaptiveThreshold(
        crop, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31, C=10,
    )
    binary = cv2.medianBlur(binary, 3)

    if out_path is None:
        out_path = os.path.join(tempfile.gettempdir(), "invoice_prep.png")
    if not cv2.imwrite(out_path, binary):
        raise IOError(f"Could not write {out_path}")
    print(
        f"[prep] {image_path} -> {out_path}  "
        f"({binary.shape[1]}x{binary.shape[0]})"
    )
    return out_path
