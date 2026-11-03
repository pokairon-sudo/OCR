# Manual Installation Guide

This guide walks you through installing the **Persian Invoice Extractor** from scratch.
Every command is copy-pasteable. Run them in order. Do not skip.

No installer script is provided — you run each command yourself so you know
exactly what is happening on your machine.

---

## Step 0 — Open a terminal

```bash
cd ~
```

---

## Step 1 — Install system packages

Pick **exactly one** sub-section below for your OS.

### 1a. Ubuntu / Debian / Linux Mint / Pop!_OS

```bash
sudo apt update
sudo apt install -y \
    python3 python3-venv python3-dev python3-pip \
    build-essential pkg-config \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    curl ca-certificates git
```

### 1b. Fedora / RHEL / Rocky / AlmaLinux / CentOS Stream

```bash
sudo dnf install -y \
    python3 python3-devel python3-pip \
    gcc gcc-c++ make pkgconf-pkg-config \
    mesa-libGL libglvnd glib2 libSM libXext libXrender \
    curl ca-certificates git
```

### 1c. Arch Linux / Manjaro / EndeavourOS

```bash
sudo pacman -Sy --needed --noconfirm \
    python python-pip \
    base-devel pkgconf \
    libglvnd glib2 libsm libxext libxrender \
    curl ca-certificates git
```

### 1d. macOS

First install Homebrew if you don't have it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then:

```bash
brew install python@3.12 curl git
```

---

## Step 2 — Verify Python is 3.11–3.13

```bash
python3 --version
```

You should see something like `Python 3.12.x`. If you see `3.14` or `3.10`, install 3.12:

- **Ubuntu/Debian**: `sudo apt install python3.12 python3.12-venv python3.12-dev`
- **Fedora/RHEL**: `sudo dnf install python3.12 python3.12-devel`
- **Arch**: `yay -S python312` (from AUR)
- **macOS**: `brew install python@3.12`

After installing, use `python3.12` instead of `python3` in the commands below.

---

## Step 3 — Create the project directory and files

```bash
mkdir -p ~/persian-invoice
cd ~/persian-invoice
```

Create the project tree:

```bash
mkdir -p invoice tests scripts
touch main.py api.py requirements.txt pyproject.toml .env
touch invoice/__init__.py invoice/schema.py invoice/utils.py invoice/preprocess.py invoice/extract.py
touch tests/__init__.py tests/test_utils.py tests/test_parse.py
touch scripts/setup_ollama_model.sh scripts/check_all.sh
```

Now paste the correct contents into each file using your editor
(`nano <file>`, `vim <file>`, or open the folder in VS Code with `code .`).

Final layout should look like:

```
~/persian-invoice/
├── main.py
├── api.py
├── requirements.txt
├── pyproject.toml
├── .env
├── invoice/
│   ├── __init__.py
│   ├── schema.py
│   ├── utils.py
│   ├── preprocess.py
│   └── extract.py
├── tests/
│   ├── __init__.py
│   ├── test_utils.py
│   └── test_parse.py
└── scripts/
    ├── setup_ollama_model.sh
    └── check_all.sh
```

---

## Step 4 — Create the Python virtual environment

```bash
cd ~/persian-invoice
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`.

Every subsequent command must be run **with this venv active**. If you close
the terminal and reopen it later, re-run:

```bash
cd ~/persian-invoice
source .venv/bin/activate
```

---

## Step 5 — Install Python dependencies

```bash
pip install --upgrade pip wheel
pip install -r requirements.txt
```

This takes 1–3 minutes. It downloads OpenCV, Pydantic, the Ollama client,
FastAPI, and pytest.

---

## Step 6 — Install Ollama

### 6a. Linux (Ubuntu, Debian, Fedora, RHEL, Arch, …)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 6b. macOS

```bash
brew install ollama
```

Or download the `.dmg` from <https://ollama.com/download>.

---

## Step 7 — Configure Ollama for 8k context

Without this step, the model silently falls back to 4096 tokens and the
vision request will fail with "context exceeded".

### 7a. Linux with systemd

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d

sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null <<'EOF'
[Service]
Environment="OLLAMA_CONTEXT_LENGTH=8192"
Environment="OLLAMA_KEEP_ALIVE=30m"
EOF

sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl restart ollama
```

### 7b. macOS

```bash
launchctl setenv OLLAMA_CONTEXT_LENGTH 8192
launchctl setenv OLLAMA_KEEP_ALIVE 30m
```

Then **quit and reopen the Ollama app** (menu-bar icon → Quit, then reopen
from Applications). Env vars only apply to newly started processes.

### 7c. Verify the daemon is responding

```bash
curl -s http://127.0.0.1:11434/api/tags
```

You should get a JSON response. If you get `Connection refused`:

- Linux: `sudo systemctl status ollama`
- macOS: open the Ollama app from Applications

---

## Step 8 — Pull the base model

```bash
ollama pull qwen2.5vl:3b
```

This downloads ~3 GB. Takes a few minutes on a normal connection.

---

## Step 9 — Build the 8k-context derivative model

```bash
ollama show qwen2.5vl:3b --modelfile > /tmp/qwen.Modelfile

if grep -q '^PARAMETER num_ctx' /tmp/qwen.Modelfile; then
    sed -i.bak 's/^PARAMETER num_ctx.*/PARAMETER num_ctx 8192/' /tmp/qwen.Modelfile
    rm -f /tmp/qwen.Modelfile.bak
else
    echo 'PARAMETER num_ctx 8192' >> /tmp/qwen.Modelfile
fi

ollama create qwen2.5vl:3b-8k -f /tmp/qwen.Modelfile
rm -f /tmp/qwen.Modelfile
```

Verify:

```bash
ollama show qwen2.5vl:3b-8k | grep -i num_ctx
```

Expected output:

```
num_ctx    8192
```

If you see `4096`, the Modelfile edit failed — re-run step 9.

---

## Step 10 — Run the unit tests (no model needed)

```bash
pytest -q
```

Expected output:

```
.......                                          [100%]
7 passed in 0.3s
```

These tests verify digit normalization and parsing logic.
If they fail, something is wrong with your Python files — do not proceed.

---

## Step 11 — Extract your first invoice

```bash
cp /path/to/your/photo.jpg ~/persian-invoice/sample.jpg
python main.py sample.jpg --debug
```

`--debug` shows the raw model output before parsing. Use it the first time
so you can see what the model is actually reading.

Expected output shape:

```
[prep] sample.jpg -> /tmp/invoice_prep.png  (1400x1867)
--- pass 1 raw ---
لیمو شیرین | 0/590 | 1 | 23000 | 13570
...
TOTAL: 1669510

======================================================================
لیمو شیرین                | وزن:0/590 تعداد:1 | واحد:     23,000 | جمع:      13,570
...
======================================================================
جمع کل: 1,669,510
```

---

## Step 12 — (Optional) Start the HTTP API

```bash
pip install '.[api]'
uvicorn api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
curl -F file=@sample.jpg http://127.0.0.1:8000/extract
```

You get JSON back.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ImportError: libGL.so.1` | Missing OpenCV runtime | Re-run step 1 for your distro |
| `ModuleNotFoundError: invoice` | Not in project root, or venv not active | `cd ~/persian-invoice && source .venv/bin/activate` |
| `Connection refused` on port 11434 | Ollama daemon not running | See step 7c |
| `exceeds the available context size` | Step 7 not applied | Re-run step 7, then restart daemon |
| `model 'qwen2.5vl:3b-8k' not found` | Step 9 not done | Run step 9 |
| Python 3.14 error on import | Unsupported version | Install 3.12 (step 2) |
| Very wrong extraction | Preprocessing wrong for your photo | See `invoice/preprocess.py`; try `INVOICE_TARGET_WIDTH=1600` |
| Model is very slow | Running on CPU | Expected on CPU; a GPU will make it 10–20× faster |

---

## Every time you come back later

Only three commands are needed:

```bash
cd ~/persian-invoice
source .venv/bin/activate
python main.py your_image.jpg
```

If the Ollama daemon was stopped (e.g. after a reboot):

```bash
sudo systemctl start ollama        # Linux
# or open Ollama.app               # macOS
```

That's it. Every command is yours to run — no hidden installer script.
