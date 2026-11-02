#!/usr/bin/env bash
# =============================================================================
# install.sh — FULLY AUTOMATIC bootstrap for the Persian Invoice Extractor
#
# Just run:   bash install.sh
# No prompts. No flags required. Detects OS, installs everything, builds the
# model, verifies, and (if a fixture image exists) performs a first run.
#
# Behaviour can be tweaked via env vars (all optional):
#   OLLAMA_MODEL        default: qwen2.5vl:3b-8k
#   OLLAMA_BASE_MODEL   default: qwen2.5vl:3b
#   OLLAMA_CTX          default: 8192
#   NO_SYSTEM=1         skip system package install
#   NO_OLLAMA=1         skip Ollama install/config
#   NO_MODEL=1          skip model pull/derivation
#   NO_VERIFY=1         skip scripts/check_all.sh
#   NO_SMOKE=1          skip the automatic first-run
# =============================================================================
set -euo pipefail

# ---------- logging ----------
RED=$'\033[0;31m'; GRN=$'\033[0;32m'; YLW=$'\033[0;33m'; BLU=$'\033[0;34m'; NC=$'\033[0m'
log()  { echo -e "\n${BLU}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GRN}✔${NC} $*"; }
warn() { echo -e "${YLW}⚠${NC} $*"; }
die()  { echo -e "${RED}✘ $*${NC}" >&2; exit 1; }

# ---------- auto-elevate (never prompts if sudo cache is already warm) ----------
ensure_root_for_system_packages() {
    [[ "${NO_SYSTEM:-0}" == "1" ]] && return 0
    [[ "$(uname -s)" == "Darwin" ]] && return 0   # brew doesn't need root
    if [[ $EUID -ne 0 ]]; then
        if sudo -n true 2>/dev/null; then
            ok "Passwordless sudo available; will use it for system packages."
        else
            warn "System package install needs root. Run once as:"
            warn "    sudo bash install.sh"
            warn "Continuing WITHOUT system packages (NO_SYSTEM=1)."
            export NO_SYSTEM=1
        fi
    fi
}

# ---------- locate project root ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
[[ -f requirements.txt ]] || die "requirements.txt not found — run from project root."
[[ -d invoice ]]          || die "invoice/ package not found — run from project root."

MODEL_NAME="${OLLAMA_MODEL:-qwen2.5vl:3b-8k}"
BASE_MODEL="${OLLAMA_BASE_MODEL:-qwen2.5vl:3b}"
CTX="${OLLAMA_CTX:-8192}"
FIXTURE_IMAGE="tests/fixtures/my_invoice_fa.jpg"

# ---------- detect OS ----------
detect_os() {
    if [[ "$(uname -s)" == "Darwin" ]]; then OS="macos"
    elif [[ -f /etc/arch-release ]]; then OS="arch"
    elif [[ -f /etc/debian_version ]]; then OS="debian"
    elif [[ -f /etc/redhat-release ]] || [[ -f /etc/fedora-release ]]; then OS="rhel"
    else OS="unknown"; fi
    log "Detected OS: ${YLW}${OS}${NC}  ($(uname -srm))"
}

# ---------- 1. system packages (unattended) ----------
install_system_packages() {
    [[ "${NO_SYSTEM:-0}" == "1" ]] && { warn "Skipping system packages (NO_SYSTEM=1)."; return; }
    [[ "$OS" == "unknown" ]] && { warn "Unknown OS; skipping system packages."; return; }

    log "Installing system packages (unattended) for $OS"
    case "$OS" in
        debian)
            export DEBIAN_FRONTEND=noninteractive
            local SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo -n"
            $SUDO apt-get -y -qq update
            $SUDO apt-get -y -qq \
                -o Dpkg::Options::="--force-confdef" \
                -o Dpkg::Options::="--force-confold" \
                install \
                python3 python3-venv python3-dev python3-pip \
                build-essential pkg-config \
                libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
                curl ca-certificates git
            ;;
        rhel)
            local SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo -n"
            $SUDO dnf -y -q install \
                python3 python3-devel python3-pip \
                gcc gcc-c++ make pkgconf-pkg-config \
                mesa-libGL libglvnd glib2 libSM libXext libXrender \
                curl ca-certificates git
            ;;
        arch)
            local SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo -n"
            $SUDO pacman -Sy --needed --noconfirm --quiet \
                python python-pip \
                base-devel pkgconf \
                libglvnd glib2 libsm libxext libxrender \
                curl ca-certificates git
            ;;
        macos)
            command -v brew >/dev/null 2>&1 || die "Homebrew required. Install from https://brew.sh"
            export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1
            brew list python@3.12 >/dev/null 2>&1 || brew install -q python@3.12
            brew list curl         >/dev/null 2>&1 || brew install -q curl
            brew list git          >/dev/null 2>&1 || brew install -q git
            ;;
    esac
    ok "System packages installed."
}

# ---------- 2. python ----------
find_python() {
    for cand in python3.12 python3.11 python3.13 python3; do
        if command -v "$cand" >/dev/null 2>&1 && \
           "$cand" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)' 2>/dev/null; then
            echo "$cand"; return 0
        fi
    done
    return 1
}

setup_venv() {
    log "Preparing Python virtual environment"
    local PY
    PY="$(find_python)" || die "No Python 3.11–3.13 found. Install python3.12 and re-run."
    if [[ ! -d .venv ]]; then
        "$PY" -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    ok "venv active: $(python --version)"

    log "Installing Python dependencies (unattended)"
    python -m pip install --upgrade --quiet pip wheel
    pip install --quiet -r requirements.txt
    ok "Python dependencies installed."
}

# ---------- 3. ollama ----------
install_ollama() {
    [[ "${NO_OLLAMA:-0}" == "1" ]] && { warn "Skipping Ollama (NO_OLLAMA=1)."; return; }

    if command -v ollama >/dev/null 2>&1; then
        ok "Ollama already installed ($(ollama --version 2>/dev/null | head -1))"
    else
        log "Installing Ollama (unattended)"
        curl -fsSL https://ollama.com/install.sh | sh
        ok "Ollama installed."
    fi

    if [[ "$OS" == "macos" ]]; then
        launchctl setenv OLLAMA_CONTEXT_LENGTH "$CTX" || true
        launchctl setenv OLLAMA_KEEP_ALIVE 30m || true
        # Best-effort: restart the GUI app if running.
        osascript -e 'quit app "Ollama"' >/dev/null 2>&1 || true
        sleep 2
        open -a Ollama >/dev/null 2>&1 || warn "Open Ollama.app manually to start the daemon."
    elif command -v systemctl >/dev/null 2>&1; then
        log "Configuring Ollama daemon (unattended)"
        local SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo -n"
        $SUDO mkdir -p /etc/systemd/system/ollama.service.d
        $SUDO tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<EOF
[Service]
Environment="OLLAMA_CONTEXT_LENGTH=$CTX"
Environment="OLLAMA_KEEP_ALIVE=30m"
EOF
        $SUDO systemctl daemon-reload
        $SUDO systemctl enable ollama >/dev/null 2>&1 || true
        $SUDO systemctl restart ollama
        ok "Ollama service configured and restarted."
    else
        warn "No systemd — starting 'ollama serve' in the background."
        nohup ollama serve >/tmp/ollama.log 2>&1 &
    fi

    log "Waiting for Ollama API on :11434"
    for _ in {1..60}; do
        if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            ok "Ollama API ready."
            return
        fi
        sleep 1
    done
    die "Ollama API did not become ready in 60s. Check 'systemctl status ollama' or ~/Library/Logs/Ollama."
}

# ---------- 4. model ----------
setup_model() {
    [[ "${NO_MODEL:-0}" == "1" ]] && { warn "Skipping model setup (NO_MODEL=1)."; return; }

    log "Pulling base model: $BASE_MODEL"
    ollama pull "$BASE_MODEL"

    log "Deriving $MODEL_NAME with num_ctx=$CTX"
    local TMP; TMP="$(mktemp)"
    ollama show "$BASE_MODEL" --modelfile > "$TMP"
    if grep -q '^PARAMETER num_ctx' "$TMP"; then
        sed -i.bak "s/^PARAMETER num_ctx.*/PARAMETER num_ctx $CTX/" "$TMP"
        rm -f "$TMP.bak"
    else
        echo "PARAMETER num_ctx $CTX" >> "$TMP"
    fi
    ollama create "$MODEL_NAME" -f "$TMP" >/dev/null
    rm -f "$TMP"

    local seen
    seen=$(ollama show "$MODEL_NAME" | grep -i num_ctx | awk '{print $NF}')
    [[ "$seen" == "$CTX" ]] && ok "Model ready: $MODEL_NAME (num_ctx=$CTX)" \
                            || die "Model num_ctx=$seen, expected $CTX"
}

# ---------- 5. verify ----------
run_verify() {
    [[ "${NO_VERIFY:-0}" == "1" ]] && { warn "Skipping verification (NO_VERIFY=1)."; return; }
    log "Running scripts/check_all.sh"
    if [[ -f scripts/check_all.sh ]]; then
        bash scripts/check_all.sh || warn "check_all.sh reported issues — see above."
    else
        warn "scripts/check_all.sh missing; skipping verify."
    fi
}

# ---------- 6. automatic first run ----------
auto_smoke() {
    [[ "${NO_SMOKE:-0}" == "1" ]] && return 0
    if [[ ! -f "$FIXTURE_IMAGE" ]]; then
        warn "No fixture image at $FIXTURE_IMAGE — skipping smoke run."
        return 0
    fi
    log "Automatic smoke test on $FIXTURE_IMAGE"
    if python main.py "$FIXTURE_IMAGE" --json >/tmp/invoice_out.json 2>/tmp/invoice_err.log; then
        ok "Smoke test produced valid JSON:"
        cat /tmp/invoice_out.json | python -m json.tool | head -40
    else
        warn "Smoke test failed. See /tmp/invoice_err.log:"
        tail -20 /tmp/invoice_err.log
    fi
}

# =============================================================================
# main
# =============================================================================
log "Persian Invoice Extractor — unattended installer"
detect_os
ensure_root_for_system_packages
install_system_packages
setup_venv
install_ollama
setup_model
run_verify
auto_smoke

echo -e "\n${GRN}════════════════════════════════════════════════════════${NC}"
echo -e "${GRN}  Installation complete — no manual steps required.${NC}"
echo -e "${GRN}════════════════════════════════════════════════════════${NC}"
echo -e "  Activate venv:  ${YLW}source .venv/bin/activate${NC}"
echo -e "  Extract:        ${YLW}python main.py <image>${NC}"
echo -e "  HTTP API:       ${YLW}uvicorn api:app --host 127.0.0.1 --port 8000${NC}"
echo -e "  Re-verify:      ${YLW}bash scripts/check_all.sh${NC}"
