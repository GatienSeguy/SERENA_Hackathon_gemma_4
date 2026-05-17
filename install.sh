#!/usr/bin/env bash
# SERENA bootstrap — macOS & Linux.
# Idempotent: safe to re-run. Installs Ollama, pulls model, creates venv,
# installs deps, then launches the web server on http://localhost:7860.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERENA_DIR="${SCRIPT_DIR}/serena"
VENV_DIR="${SERENA_DIR}/.venv"
MODEL_TAG="${SERENA_MODEL:-gemma4:e2b}"
MIN_PY=10   # 3.10
MAX_PY=12   # 3.12 (3.13+ has known issues per README)

log()  { printf "\033[1;36m[serena]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m[fail]\033[0m %s\n" "$*" >&2; exit 1; }

OS="$(uname -s)"
case "${OS}" in
  Darwin) PLATFORM=mac   ;;
  Linux)  PLATFORM=linux ;;
  *) die "Unsupported OS: ${OS}. Use install.ps1 on Windows or run inside WSL." ;;
esac

# ─── 1. Ollama install ───────────────────────────────────────────
if ! command -v ollama >/dev/null 2>&1; then
  log "Ollama not found. Installing…"
  if [[ "${PLATFORM}" == "mac" ]]; then
    if command -v brew >/dev/null 2>&1; then
      brew install ollama
    else
      die "Homebrew not found. Install from https://brew.sh then re-run, or download Ollama.app from https://ollama.com/download."
    fi
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi
else
  log "Ollama present ($(ollama --version 2>/dev/null | head -1))."
fi

# ─── 2. Ollama daemon ────────────────────────────────────────────
if ! curl -fsS --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
  log "Starting Ollama daemon in background…"
  if [[ "${PLATFORM}" == "mac" ]] && [[ -d "/Applications/Ollama.app" ]]; then
    open -a Ollama
  else
    nohup ollama serve >/tmp/ollama-serena.log 2>&1 &
  fi
  for i in {1..30}; do
    sleep 1
    if curl -fsS --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
      break
    fi
    [[ $i -eq 30 ]] && die "Ollama daemon did not start (see /tmp/ollama-serena.log)."
  done
fi
log "Ollama daemon reachable."

# ─── 3. Pull model ───────────────────────────────────────────────
if ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "${MODEL_TAG}"; then
  log "Model ${MODEL_TAG} already pulled."
else
  log "Pulling ${MODEL_TAG} (~2GB, one-time)…"
  ollama pull "${MODEL_TAG}"
fi

# ─── 4. Python interpreter ───────────────────────────────────────
# Validate candidate: right version + working stdlib (pyexpat/ssl/venv/ensurepip).
# Homebrew sometimes ships a Python with mismatched libexpat — silently breaks venv.
validate_py() {
  local cand="$1"
  command -v "${cand}" >/dev/null 2>&1 || return 1
  local minor
  minor=$("${cand}" -c 'import sys;print(sys.version_info.minor)' 2>/dev/null) || return 1
  (( minor >= MIN_PY && minor <= MAX_PY )) || return 1
  "${cand}" -c 'import ssl, venv, ensurepip, pyexpat' >/dev/null 2>&1 || return 1
  return 0
}

PY=""
CANDIDATES=(python3.12 python3.11 python3.10)
# Also try pyenv shims + python3 fallback last
command -v python3 >/dev/null 2>&1 && CANDIDATES+=(python3)
for cand in "${CANDIDATES[@]}"; do
  if validate_py "${cand}"; then PY="${cand}"; break; fi
done
if [[ -z "${PY}" ]]; then
  warn "No working Python 3.${MIN_PY}–3.${MAX_PY} found."
  warn "Detected interpreters were missing or had broken stdlib (often libexpat mismatch on Homebrew)."
  warn "Fix one of:"
  warn "  brew reinstall python@3.12   # macOS Homebrew"
  warn "  curl https://pyenv.run | bash && pyenv install 3.12   # pyenv"
  die  "Re-run ./install.sh after installing a working Python."
fi
log "Using ${PY} ($(${PY} --version))."

# ─── 5. venv + deps ──────────────────────────────────────────────
# Recreate venv if missing OR incomplete (activate script absent → previous run failed).
if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
  if [[ -d "${VENV_DIR}" ]]; then
    log "Removing incomplete venv at ${VENV_DIR}…"
    rm -rf "${VENV_DIR}"
  fi
  log "Creating venv at ${VENV_DIR}…"
  if ! "${PY}" -m venv "${VENV_DIR}"; then
    rm -rf "${VENV_DIR}"
    die "venv creation failed with ${PY}. Try: ${PY} -m venv /tmp/_t  (to see real error)"
  fi
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --quiet --upgrade pip
log "Installing requirements…"
pip install --quiet -r "${SERENA_DIR}/requirements.txt"

# ─── 6. Launch ───────────────────────────────────────────────────
log "Launching SERENA on http://localhost:7860"
cd "${SERENA_DIR}/web"
exec python run.py
