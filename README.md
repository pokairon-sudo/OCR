# Persian invoice extractor

Extracts line items, quantities, and grand totals from Persian (Farsi)
grocery receipt photos using a local vision LLM (`qwen2.5vl:3b` via Ollama).

## How it works

1. **Preprocess** — auto-crop to receipt, upscale to 1400 px width,
   adaptive binarize. This step is ~80% of the accuracy.
2. **Pass 1** — vision call with a rigid pipe format
   (`name | weight | qty | unit | total`). Explicitly forbids arithmetic
   to prevent digit hallucination.
3. **Pass 2** — deterministic regex parses Pass 1 into a Pydantic `Invoice`.
   No LLM, so numbers pass through untouched.
4. **Retry** — if `Σ(row totals) ≠ TOTAL`, one focused re-read that tells
   the model the expected digit count.

## Install (from zero)

```bash
# 1. system prerequisites (Debian/Ubuntu example)
sudo apt update && sudo apt install -y \
    python3.12 python3.12-venv python3.12-dev \
    build-essential pkg-config libgl1 libglib2.0-0 \
    libsm6 libxext6 libxrender1 curl ca-certificates

# 2. project
mkdir -p persian-invoice && cd persian-invoice
# (create the files from the deploy guide)
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Ollama
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl edit ollama
# in the editor, add:
#   [Service]
#   Environment="OLLAMA_CONTEXT_LENGTH=8192"
#   Environment="OLLAMA_KEEP_ALIVE=30m"
sudo systemctl daemon-reload
sudo systemctl restart ollama

# 4. build the derived model
chmod +x scripts/*.sh
bash scripts/setup_ollama_model.sh

# 5. verify
bash scripts/check_all.sh

# 6. run
python main.py my_invoice_fa.jpg --debug
```

### macOS notes

- Ollama: install the `.dmg` from ollama.com. Set env via
  `launchctl setenv OLLAMA_CONTEXT_LENGTH 8192` before launching.
- No systemd; run `ollama serve` in a terminal or use `brew services`.

### Arch notes

- Ollama: `sudo pacman -S ollama` (community repo) or `yay -S ollama-bin`.
- Python 3.12: `sudo pacman -S python312` (AUR) or pyenv.
- Service: `sudo systemctl enable --now ollama`.

### RHEL/Fedora notes

- Ollama: same install script as Ubuntu.
- `sudo dnf install python3.12 python3.12-devel gcc mesa-libGL libglvnd`.

## CLI usage

```bash
python main.py receipt.jpg              # human-readable
python main.py receipt.jpg --json       # JSON only
python main.py receipt.jpg --debug      # show raw model output
```

## HTTP API

```bash
pip install '.[api]'
uvicorn api:app --host 127.0.0.1 --port 8000

curl -F file=@receipt.jpg http://127.0.0.1:8000/extract
```

## Configuration (`.env`)

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `qwen2.5vl:3b-8k` | Derived model name |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama endpoint |
| `INVOICE_TARGET_WIDTH` | `1400` | Preprocess upscale target |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8000` | FastAPI bind |

## Known limitations

- 3B model + glossy paper: ~4/5 rows correct on first pass, 5/5 after
  retry ~70% of the time.
- Fabric background is removed by brightness threshold; strongly-shadowed
  photos fall back to full frame.
- Persian ligatures (e.g. `لا`) sometimes confuse the model
  (`اول` ↔ `اوا`) — not fixable by prompt.

## Tests

```bash
pytest -q
bash scripts/check_all.sh
```
