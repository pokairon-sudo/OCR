"""Two-pass extraction: literal transcription, then deterministic parsing.

Why not one JSON pass? Because a 3B model asked to return JSON will
re-type every digit it reads, and it re-types them wrong ~15% of the time.
Pass 1 emits a rigid pipe format; Pass 2 is regex (not an LLM), so
numbers pass through unmodified.
"""

from __future__ import annotations

import re
from typing import Optional

import ollama

from .schema import Invoice, LineItem
from .utils import clean_int, normalize_digits

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PASS1_PROMPT = """You are a literal OCR reader for a Persian grocery receipt.

Read the receipt and output ONE line per item:

    <name> | <weight> | <quantity> | <unit_price> | <total>

Columns (right→left on the receipt):
- نام کالا → <name>:      Persian text, preserve spaces.
- وزن/تعداد → split:      if the cell looks like "0/590" it's weight (kg),
                          if it's a small integer like "2" it's quantity.
- فی → <unit_price>:      price per kg in Toman.
- جمع → <total>:          printed row total.

CRITICAL RULES:
1. NEVER compute. Copy what is PRINTED, not what arithmetic implies.
2. NEVER merge words. "لیمو شیرین" stays "لیمو شیرین".
3. Use Latin digits (0-9), not Persian/Arabic digits.
4. Grand totals are LARGE INTEGERS (millions of Toman). A 6- or 7-digit
   number with no decimal point. Do NOT add or drop zeros.
5. After all item lines, emit exactly one line:
       TOTAL: <جمع کل digits>

Output ONLY the lines. No markdown, no explanations."""

PASS1_RETRY_PROMPT = """Re-read this Persian receipt carefully.

Your previous attempt summed the row totals to {line_sum:,} Toman but the
printed جمع کل is a {digits}-digit number in the millions.

Read ONLY the following lines again and copy each digit literally:
  1. The جمع column of every row (rightmost column).
  2. The جمع کل at the bottom.

Output format identical to before (pipe-delimited lines, then TOTAL:).
Do not compute anything. Do not guess. Copy what you see."""

# ---------------------------------------------------------------------------
# Ollama wrapper
# ---------------------------------------------------------------------------

def _chat(model: str, prompt: str, image_path: Optional[str]) -> str:
    msg: dict = {"role": "user", "content": prompt}
    if image_path:
        msg["images"] = [image_path]
    resp = ollama.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a literal OCR engine. You copy, never compute.",
            },
            msg,
        ],
        options={
            "temperature": 0.0,
            "num_ctx": 8192,
            "num_predict": 800,
        },
    )
    content = (resp.get("message") or {}).get("content") or ""
    if not content.strip():
        raise RuntimeError("Ollama returned empty content")
    return normalize_digits(content).strip()

# ---------------------------------------------------------------------------
# Deterministic parsing (no LLM)
# ---------------------------------------------------------------------------

_HEADER_WORDS = {"نام کالا", "ردیف", "جمع", "کالا", "-", ""}


def parse_lines(text: str) -> Invoice:
    items: list[LineItem] = []
    grand = "0"

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[`|#\-\s]+", "", line)
        line = re.sub(r"[`|\s]+$", "", line)

        m = re.match(r"^TOTAL\s*[:：]\s*(.+)$", line, re.IGNORECASE)
        if m:
            grand = m.group(1).strip()
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        while len(parts) < 5:
            parts.append("-")
        name, weight, qty, unit, total = parts[:5]

        if name in _HEADER_WORDS and total in _HEADER_WORDS:
            continue

        items.append(
            LineItem(
                name=name,
                weight="" if weight in {"-", ""} else weight,
                quantity="" if qty in {"-", ""} else qty,
                unit_price=unit,
                total_price=total,
            )
        )

    if grand in {"0", "", "-"}:
        grand = str(sum(clean_int(it.total_price) for it in items))
    return Invoice(items=items, grand_total=grand)

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def extract(image_path: str, model: str, debug: bool = False) -> Invoice:
    raw = _chat(model, PASS1_PROMPT, image_path)
    if debug:
        print("--- pass 1 raw ---\n" + raw)

    inv = parse_lines(raw)
    line_sum = sum(clean_int(it.total_price) for it in inv.items)
    grand = clean_int(inv.grand_total)

    if grand and abs(line_sum - grand) > max(50, grand * 0.02):
        print(f"[warn] sum={line_sum:,} != TOTAL={grand:,} — retrying")
        digits = len(str(grand))
        prompt = PASS1_RETRY_PROMPT.format(line_sum=line_sum, digits=digits)
        raw2 = _chat(model, prompt, image_path)
        if debug:
            print("--- pass 1 retry ---\n" + raw2)
        inv = parse_lines(raw2)

    return inv
