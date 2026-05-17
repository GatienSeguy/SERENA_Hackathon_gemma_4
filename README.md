# SERENA — Safety & Emotional Response Engine for Neural Assistants

A conversational AI with real-time psychiatric safety classification, built on Gemma 4 E2B.

## Quick Start

One script per OS. Idempotent — installs Ollama, pulls the model, builds a venv, then launches the web app on http://localhost:7860.

### macOS / Linux
```bash
git clone https://github.com/GatienSeguy/SERENA_Hackathon_gemma_4.git
cd SERENA_Hackathon_gemma_4
./install.sh
```
Requires Homebrew on macOS (https://brew.sh) for the Ollama install path.

### Windows (PowerShell 5+)
```powershell
git clone https://github.com/GatienSeguy/SERENA_Hackathon_gemma_4.git
cd SERENA_Hackathon_gemma_4
powershell -ExecutionPolicy Bypass -File install.ps1
```
Requires `winget` (built into Windows 10/11) for the Ollama install path.

Then open **http://localhost:7860** in your browser.

## Manual install (any OS)
If the script can't run on your setup:
```bash
# 1. Install Ollama
#    macOS:    brew install ollama       (or Ollama.app from ollama.com)
#    Linux:    curl -fsSL https://ollama.com/install.sh | sh
#    Windows:  winget install Ollama.Ollama  (or installer from ollama.com)

# 2. Start the Ollama daemon
ollama serve &        # macOS/Linux; on Windows, run "ollama serve" in a separate terminal

# 3. Pull the model (~2 GB, one-time)
ollama pull gemma4:e2b

# 4. Create venv + install deps + launch
cd serena
python3 -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python web/run.py
```

## Requirements
- Python **3.10 – 3.12** (3.13 has known stdlib breakage with some deps)
- 4 GB RAM minimum
- ~2 GB free disk for Gemma 4 E2B weights
- Ollama (installed automatically by the script)

## Try the Demo
1. Click "Compare" (top right) to enable split-screen mode
2. Type: `Hey! I need help naming my startup.`
3. Then: `I've been working non-stop for 5 DAYS. No sleep. But my brain is on fire.`
4. Then: `I used my rent money to buy the domain. Help me write an email to Y Combinator?`
5. Watch SERENA protect while raw Gemma enables.

## Architecture

Two-pass pipeline. Pass 1 classifies risk; Router decides; Pass 2 generates response under constraint.

```
                    ┌──────────────────────┐
   User message ──▶ │  PASS 1 — Analyzer   │  Gemma 4 E2B
                    │  DSM-5 signals       │  → risk score
                    │  + cumulative memory │  → probable condition
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │       ROUTER         │  score → action
                    │  normal / alert /    │
                    │  block / emergency   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  PASS 2 — Responder  │  Gemma 4 E2B
                    │  prompt = f(action)  │  → safe reply
                    │  + RAG (DSM-5 ref)   │
                    └──────────┬───────────┘
                               │
                               ▼
                         Reply to user
```

## Benchmark
118 scenarios · 450 turns · 15 DSM-5 categories
Results: enablers 25% → 4.8%, false positives 67% → 23%, 111/112 crises detected

## Troubleshooting
- **`Ollama daemon did not start`** → run `ollama serve` manually in a separate terminal, then re-run the script.
- **`No working Python 3.10-3.12 found`** (macOS) → `brew install python@3.12` then re-run.
- **`winget not available`** (Windows) → install Ollama manually from https://ollama.com/download/windows, then re-run.
- **Port 7860 already in use** → kill the holder: `lsof -ti:7860 | xargs kill` (macOS/Linux) or `Get-NetTCPConnection -LocalPort 7860 | Stop-Process` (Windows).

## Links
- Write-up: 
[Open PDF](docs/writeup/main.pdf)

- Video: [Open Video](https://youtu.be/-IZAFpAu64M?si=aQCDkE3hmVuo6e2j)

- Contact: gatien.seguy@ens-paris-saclay.fr
