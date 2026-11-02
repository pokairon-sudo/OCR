from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

import cv2
import ollama
from pydantic import BaseModel, Field, field_validator


# ===========================================================================
# Text helpers
# ===========================================================================

_PERSIAN = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC = "٠١٢٣٤٥٦٧٨٩"
_ENGLISH = "0123456789"
_TRANS = str.maketrans(_PERSIAN + _ARABIC, _ENGLISH * 2)


def normalize_digits(text: str) -> str:
    return str(text).translate(_TRANS)


def clean_int(val) -> int:
    if val is None:
        return 0
    if isinstance(val, int):
        return val
    s = normalize_digits(str(val))
    s = s.replace("،", "").replace(",", "").replace("٬", "").replace("\u200c", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s.strip()):
        s = s.replace(".", "")
    m = re.search(r"\d+", s)
    return int(m.group()) if m else 0


# ===========================================================================
# Image preprocessing — MINIMAL, no upscale, no sharpening
# ===========================================================================
# A 3B model chokes on 4k-token images. We only:
#  - resize to <=1024 on the long side (keeps ~1000 vision tokens)
#  - grayscale + mild CLAHE (helps legibility, doesn't add tokens)
# That's it. No unsharp mask (it amplifies JPEG noise from the fabric bg).

MAX_SIDE = 1024


def preprocess(image_path: str) -> str:
    if not os.path.isfile(image_path):
        raise FileNotFoundError(image_path)
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"cv2 cannot decode {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    longest = max(h, w)
    if longest > MAX_SIDE:
        s = MAX_SIDE / longest
        gray = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)

    # Crop to the invoice area roughly: invoices in photos are usually
    # centered. Skip if you already have a tight crop.
    # gray = auto_crop(gray)  # optional

    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    out = clahe.apply(gray)

    path = os.path.join(tempfile.gettempdir(), "invoice_prep.png")
    cv2.imwrite(path, out)
    print(f"[prep] {image_path} -> {path}  ({out.shape[1]}x{out.shape[0]})")
    return path


# ===========================================================================
# Schema — keep weight and count separate!
# ===========================================================================

class LineItem(BaseModel):
    name: str = Field(description="Product name, spaces preserved")
    weight: str = Field(default="", description="وزن column, e.g. 0.590; empty if blank")
    quantity: str = Field(default="", description="تعداد column, e.g. 2; empty if blank")
    unit_price: str = Field(default="0", description="قیمت واحد, printed digits only")
    total_price: str = Field(default="0", description="جمع column, printed digits only")

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        return re.sub(r"\s+", " ", str(v)).strip()


class Invoice(BaseModel):
    items: list[LineItem] = Field(default_factory=list)
    grand_total: str = Field(default="0", description="جمع کل")
    total_weight: str = Field(default="", description="وزن کل, e.g. 4.570 kg")


# ===========================================================================
# Pass 1 — line-by-line transcription (no table, no math)
# ===========================================================================

PASS1_PROMPT = """You are a careful OCR reader for a Persian grocery receipt.

READ the receipt image and output ONE line per item, in this exact format:

    <name> | <weight> | <quantity> | <unit_price> | <total>

Where each `<...>` is copied EXACTLY from the corresponding column:

- <name>:       نام کالا column. Keep spaces between words. Persian, not transliterated.
- <weight>:     وزن column (often a decimal like 0.590). If blank, write "-".
- <quantity>:   تعداد column (integer like 1, 2, 3). If blank, write "-".
- <unit_price>: قیمت واحد column. Copy digits EXACTLY, do not add/remove zeros.
- <total>:      جمع column. Copy digits EXACTLY from the printed total.

CRITICAL RULES:
1. Do NOT compute anything. Copy what is PRINTED, not what you think it should be.
2. Do NOT merge words. "لیمو شیرین" must stay "لیمو شیرین".
3. Output Latin digits (0-9), not Persian/Arabic digits.
4. Do NOT output a header, separator row, or "ردیف".
5. After the item lines, output exactly one final line:
    TOTAL: <جمع کل digits>

Example of valid output:
لیمو شیرین | 0.590 | - | 23000 | 13570
خیار شمال | 0.760 | - | 12600 | 9576
TOTAL: 1669510

Now transcribe the image. Nothing else — no explanation, no markdown."""


def pass1_transcribe(image_path: str, model: str) -> str:
    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": "You are a literal OCR engine. You copy, never compute."},
            {"role": "user", "content": PASS1_PROMPT, "images": [image_path]},
        ],
        options={"temperature": 0.0, "num_ctx": 8192, "num_predict": 800},
    )
    content = (resp.get("message") or {}).get("content") or ""
    if not content.strip():
        raise RuntimeError("Pass 1 returned empty content")
    return normalize_digits(content).strip()


# ===========================================================================
# Pass 2 — parse Pass 1's plain text into Invoice (deterministic, not LLM)
# ===========================================================================
# This pass uses regex, NOT an LLM. It's 100% accurate given well-formed
# input, and it prevents the "digit hallucination" problem of pass 2 in the
# original code (where the LLM re-typed numbers it had just read).

def parse_pass1_text(text: str) -> Invoice:
    items: list[LineItem] = []
    grand = "0"

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # strip markdown artifacts
        line = re.sub(r"^[\|\-\s#]+", "", line)
        line = re.sub(r"[\|\s]+$", "", line)

        m = re.match(r"^TOTAL\s*[:：]\s*(.+)$", line, re.IGNORECASE)
        if m:
            grand = m.group(1).strip()
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        # pad missing trailing fields
        while len(parts) < 5:
            parts.append("-")

        name, weight, qty, unit, total = parts[:5]
        # Skip header-ish rows
        if name in {"نام کالا", "ردیف", "-", ""} and total in {"جمع", "-", ""}:
            continue

        items.append(LineItem(
            name=name,
            weight="" if weight in {"-", ""} else weight,
            quantity="" if qty in {"-", ""} else qty,
            unit_price=unit,
            total_price=total,
        ))

    # If grand total wasn't printed, compute from line sums
    if grand in {"0", "", "-"}:
        grand = str(sum(clean_int(it.total_price) for it in items))

    return Invoice(items=items, grand_total=grand)


# ===========================================================================
# Pass 3 — validation & correction loop
# ===========================================================================
# If the sum of line totals doesn't match TOTAL, retry Pass 1 once with
# the suspected rows highlighted. Small models self-correct well when you
# point at the specific row that's wrong.

PASS1_RETRY_PROMPT = """The previous transcription is internally inconsistent:

  - Sum of the 'جمع' (total) column: {line_sum}
  - Printed TOTAL: {grand}

These must be equal. Re-read the image and re-transcribe ONLY the rows you
are unsure about. Be extremely careful with each digit. Output the SAME
format as before (pipe-delimited, one line per item, then TOTAL: ...).
Here is the previous attempt for reference:

{previous}

Now output the corrected transcription."""


def pass1_retry(image_path: str, model: str, previous: str,
                line_sum: int, grand: int) -> str:
    prompt = PASS1_RETRY_PROMPT.format(
        line_sum=f"{line_sum:,}", grand=f"{grand:,}", previous=previous,
    )
    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": "You are a literal OCR engine. You copy, never compute."},
            {"role": "user", "content": prompt, "images": [image_path]},
        ],
        options={"temperature": 0.0, "num_ctx": 8192, "num_predict": 800},
    )
    return normalize_digits(
        (resp.get("message") or {}).get("content") or ""
    ).strip()


def extract(image_path: str, model: str, debug: bool = False) -> Invoice:
    prepped = preprocess(image_path)

    print("[pass 1] transcribing...")
    raw = pass1_transcribe(prepped, model)
    if debug:
        print("--- pass 1 raw ---\n" + raw)
    inv = parse_pass1_text(raw)

    line_sum = sum(clean_int(it.total_price) for it in inv.items)
    grand = clean_int(inv.grand_total)

    if grand and abs(line_sum - grand) > max(10, grand * 0.02):
        print(f"[warn] sum(lines)={line_sum:,} != TOTAL={grand:,} — retrying")
        raw2 = pass1_retry(prepped, model, raw, line_sum, grand)
        if debug:
            print("--- pass 1 retry ---\n" + raw2)
        inv = parse_pass1_text(raw2)

    return inv


# ===========================================================================
# CLI
# ===========================================================================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--model", default="qwen2.5vl:3b-8k")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)

    inv = extract(args.image, args.model, args.debug)

    print("\n" + "=" * 70)
    for it in inv.items:
        wt = f"وزن:{it.weight}" if it.weight else ""
        qt = f"تعداد:{it.quantity}" if it.quantity else ""
        extra = " ".join(x for x in (wt, qt) if x) or "-"
        print(f"{it.name:<25} | {extra:<15} | "
              f"واحد: {clean_int(it.unit_price):>10,} | "
              f"جمع: {clean_int(it.total_price):>10,}")
    print("=" * 70)
    grand = clean_int(inv.grand_total)
    line_sum = sum(clean_int(it.total_price) for it in inv.items)
    print(f"جمع کل: {grand:,}")
    if grand != line_sum:
        print(f"⚠  line sum = {line_sum:,} (diff {line_sum - grand:+,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
