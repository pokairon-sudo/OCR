#!/usr/bin/env bash
# Cross-platform env checker: Arch, Debian/Ubuntu, RHEL/Fedora/Rocky/Alma.
set -uo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0
ok()   { echo -e "  ${GRN}✔${NC} $*"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}✘${NC} $*"; FAIL=$((FAIL+1)); }
warn() { echo -e "  ${YLW}⚠${NC} $*"; WARN=$((WARN+1)); }
section() { echo -e "\n${BLU}▶ $*${NC}"; }

detect_distro() {
    if [[ -f /etc/arch-release ]]; then DISTRO="arch"
    elif [[ -f /etc/debian_version ]]; then DISTRO="debian"
    elif [[ -f /etc/redhat-release ]] || [[ -f /etc/fedora-release ]]; then DISTRO="rhel"
    else DISTRO="unknown"; fi
    echo -e "Detected distro family: ${YLW}${DISTRO}${NC}"
    echo -e "OS: $(uname -srm)"
}

check_system_deps() {
    section "1/5 System dependencies"
    if ldconfig -p 2>/dev/null | grep -q 'libGL\.so\.1'; then
        ok "libGL.so.1 present"
    else
        case "$DISTRO" in
            debian) fail "libGL.so.1 missing → sudo apt install libgl1 libglib2.0-0" ;;
            rhel)   fail "libGL.so.1 missing → sudo dnf install mesa-libGL libglvnd" ;;
            arch)   fail "libGL.so.1 missing → sudo pacman -S libglvnd" ;;
            *)      fail "libGL.so.1 missing (unknown distro)" ;;
        esac
    fi
    command -v curl >/dev/null 2>&1 \
        && ok "curl present ($(curl --version | head -1 | awk '{print $2}'))" \
        || fail "curl missing"
    command -v ollama >/dev/null 2>&1 \
        && ok "ollama binary present" \
        || fail "ollama binary missing → curl -fsSL https://ollama.com/install.sh | sh"
}

check_ollama() {
    section "2/5 Ollama service & model"
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        ok "Ollama API reachable on :11434"
    else
        fail "Ollama API unreachable → sudo systemctl start ollama"
        return
    fi
    if ollama list 2>/dev/null | grep -q 'qwen2.5vl:3b-8k'; then
        ok "Model qwen2.5vl:3b-8k listed"
    else
        fail "Model missing → bash scripts/setup_ollama_model.sh"
        return
    fi
    local ctx
    ctx=$(ollama show qwen2.5vl:3b-8k 2>/dev/null | grep -i 'num_ctx' | awk '{print $NF}')
    [[ "$ctx" == "8192" ]] && ok "num_ctx = 8192" || fail "num_ctx = ${ctx:-unknown}, expected 8192"
}

check_python() {
    section "3/5 Python environment"
    [[ -n "${VIRTUAL_ENV:-}" ]] && ok "Virtualenv active: $VIRTUAL_ENV" \
                                || warn "No virtualenv active"
    local pyver
    pyver=$(python3 --version 2>&1 | awk '{print $2}')
    if python3 -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)' 2>/dev/null; then
        ok "Python $pyver (supported)"
    else
        fail "Python $pyver not in 3.11–3.13"
    fi
    for pkg in cv2 ollama pydantic dotenv; do
        python3 -c "import $pkg" 2>/dev/null && ok "import $pkg" \
                                            || fail "import $pkg failed → pip install -r requirements.txt"
    done
    python3 -c "from invoice import extract, preprocess" 2>/dev/null \
        && ok "Project package importable" \
        || fail "Cannot import 'invoice' → run from project root"
}

check_project() {
    section "4/5 Project files"
    for f in main.py requirements.txt invoice/extract.py invoice/preprocess.py invoice/schema.py; do
        [[ -f "$f" ]] && ok "$f" || fail "$f missing"
    done
    command -v pytest >/dev/null 2>&1 || { warn "pytest not installed"; return; }
    pytest -q --no-header 2>/dev/null | tail -1 | grep -q 'passed' \
        && ok "pytest suite passes" \
        || fail "pytest suite has failures → run pytest -q"
}

check_smoke() {
    section "5/5 Smoke test"
    local fixture="tests/fixtures/my_invoice_fa.jpg"
    [[ -f "$fixture" ]] || { warn "No test image at $fixture"; return; }
    local out
    out=$(python3 main.py "$fixture" --json 2>/dev/null)
    echo "$out" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null \
        && ok "End-to-end JSON extraction succeeded" \
        || fail "End-to-end extraction failed → python3 main.py $fixture --debug"
}

summary() {
    echo -e "\n${BLU}════════════════════════════════════════════════════════${NC}"
    echo -e "  ${GRN}PASS: $PASS${NC}   ${RED}FAIL: $FAIL${NC}   ${YLW}WARN: $WARN${NC}"
    echo -e "${BLU}════════════════════════════════════════════════════════${NC}"
    [[ $FAIL -gt 0 ]] && { echo -e "${RED}Critical failures.${NC}"; exit 1; }
    echo -e "${GRN}Environment OK.${NC}"
    exit 0
}

detect_distro
check_system_deps
check_ollama
check_python
check_project
check_smoke
summary
