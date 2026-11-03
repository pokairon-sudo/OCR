"""Digit normalization and price parsing.

Pure functions with no side effects — tested in tests/test_utils.py.
Deliberately keep this file free of Ollama/OpenCV imports so it can be
reused from a web API, a CLI, or a notebook without pulling heavy deps.
"""

from __future__ import annotations

import re

_PERSIAN = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC = "٠١٢٣٤٥٦٧٨٩"
_ENGLISH = "0123456789"
_TRANS = str.maketrans(_PERSIAN + _ARABIC, _ENGLISH * 2)


def normalize_digits(text: str) -> str:
    """Convert Persian (۰–۹) and Arabic-Indic (٠–٩) digits to ASCII."""
    return str(text).translate(_TRANS)


def clean_int(val) -> int:
    """Best-effort: extract the first integer from any price string.

    Handles:
      * Persian comma (،), Arabic thousands separator (٬), ASCII comma (,)
      * Dot-grouped thousands ("1.669.510" → 1669510)
      * ZWNJ characters that Persian digits sometimes carry
      * Trailing currency words ("تومان", "ریال")
    """
    if val is None:
        return 0
    if isinstance(val, int):
        return val
    s = (
        normalize_digits(str(val))
        .replace("،", "")
        .replace(",", "")
        .replace("٬", "")
        .replace("\u200c", "")
        .replace(" ", "")
    )
    # If the dots are thousand-groupers (groups of 3), strip them.
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s.strip()):
        s = s.replace(".", "")
    m = re.search(r"\d+", s)
    return int(m.group()) if m else 0
