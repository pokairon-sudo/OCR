#!/usr/bin/env python3
"""CLI entry point. All logic lives in the `invoice` package."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from invoice.extract import extract
from invoice.preprocess import preprocess
from invoice.utils import clean_int


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    ap = argparse.ArgumentParser(
        description="Extract line items from a Persian grocery receipt photo."
    )
    ap.add_argument("image", help="Path to the receipt image")
    ap.add_argument(
        "--model",
        default=os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b-8k"),
        help="Ollama model name (default from .env)",
    )
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--json", action="store_true", help="Emit JSON only")
    args = ap.parse_args(argv)

    prepped = preprocess(
        args.image,
        target_width=int(os.getenv("INVOICE_TARGET_WIDTH", "1400")),
    )
    inv = extract(prepped, args.model, debug=args.debug)

    if args.json:
        print(json.dumps(inv.model_dump(), ensure_ascii=False, indent=2))
        return 0

    print("\n" + "=" * 70)
    for it in inv.items:
        wt = f"وزن:{it.weight}" if it.weight else ""
        qt = f"تعداد:{it.quantity}" if it.quantity else ""
        extra = " ".join(x for x in (wt, qt) if x) or "-"
        print(
            f"{it.name:<25} | {extra:<15} | "
            f"واحد: {clean_int(it.unit_price):>10,} | "
            f"جمع: {clean_int(it.total_price):>10,}"
        )
    print("=" * 70)
    grand = clean_int(inv.grand_total)
    line_sum = sum(clean_int(i.total_price) for i in inv.items)
    print(f"جمع کل: {grand:,}")
    if grand != line_sum:
        print(f"⚠  line sum={line_sum:,}  diff={line_sum - grand:+,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
