"""Minimal FastAPI wrapper around the extractor.

Run:
    uvicorn api:app --host 0.0.0.0 --port 8000

POST /extract with multipart/form-data field "file".
"""

from __future__ import annotations

import os
import tempfile

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from invoice.extract import extract
from invoice.preprocess import preprocess

load_dotenv()

app = FastAPI(title="Persian Invoice Extractor", version="0.1.0")

MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b-8k")
TARGET_WIDTH = int(os.getenv("INVOICE_TARGET_WIDTH", "1400"))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL}


@app.post("/extract")
async def extract_endpoint(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    suffix = os.path.splitext(file.filename)[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        prepped = preprocess(tmp_path, target_width=TARGET_WIDTH)
        inv = extract(prepped, MODEL, debug=False)
        return JSONResponse(inv.model_dump())
    except Exception as e:
        raise HTTPException(500, f"Extraction failed: {e}")
    finally:
        for p in (tmp_path, prepped if "prepped" in locals() else None):
            if p and os.path.exists(p):
                os.remove(p)
