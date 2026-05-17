"""SERENA — Fine-tune Gemma with MLX-LM LoRA on Apple Silicon (M1/M2/M3/M4).

Native Mac path. Use this when Unsloth is not available (no NVIDIA GPU).

Setup:
    pip install mlx-lm

Usage:
    python finetune/train_mlx.py            # convert data + run training
    python finetune/train_mlx.py --convert  # only convert train/val.json -> JSONL
    python finetune/train_mlx.py --fuse     # merge LoRA into a single model
    python finetune/train_mlx.py --gguf     # convert fused model to GGUF (Ollama)

Output:
    finetune/mlx_data/{train,valid}.jsonl   — chat-format JSONL
    finetune/serena-lora-mlx/               — adapter weights
    finetune/serena-fused/                  — fused full model (after --fuse)
    finetune/serena-gguf/                   — GGUF for Ollama (after --gguf)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAIN_JSON = HERE / "train.json"
VAL_JSON = HERE / "val.json"
MLX_DATA = HERE / "mlx_data"
ADAPTER_OUT = HERE / "serena-lora-mlx"
FUSED_OUT = HERE / "serena-fused"
GGUF_OUT = HERE / "serena-gguf"

# Default model — change to gemma 4 E2B HF id when published.
# mlx-community ships pre-converted MLX weights.
BASE_MODEL = "mlx-community/gemma-2-2b-it-4bit"


# ──────────────────────────────────────────────────────────────────────
# 1. Convert train.json / val.json → JSONL with {"messages": [...]}.
# ──────────────────────────────────────────────────────────────────────

def convert_to_jsonl() -> None:
    if not TRAIN_JSON.exists() or not VAL_JSON.exists():
        sys.exit(
            f"Missing {TRAIN_JSON} or {VAL_JSON}. "
            "Run finetune/generate_dataset.py first."
        )

    MLX_DATA.mkdir(exist_ok=True)
    for src, dst_name in [(TRAIN_JSON, "train.jsonl"), (VAL_JSON, "valid.jsonl")]:
        data = json.loads(src.read_text(encoding="utf-8"))
        out_path = MLX_DATA / dst_name
        with out_path.open("w", encoding="utf-8") as f:
            for ex in data:
                line = {"messages": ex["conversations"]}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        print(f"  {dst_name}: {len(data)} examples → {out_path}")


# ──────────────────────────────────────────────────────────────────────
# 2. Run mlx_lm.lora training.
# ──────────────────────────────────────────────────────────────────────

def _ensure_mlx_lm() -> None:
    try:
        import mlx_lm  # noqa: F401
    except ImportError:
        sys.exit(
            "ERROR: mlx-lm not installed.\n"
            "Install:  pip install mlx-lm\n"
            "Note: requires Python >= 3.9 on Apple Silicon."
        )


def run_training(model: str = BASE_MODEL, iters: int = 600) -> None:
    _ensure_mlx_lm()
    ADAPTER_OUT.mkdir(exist_ok=True)
    cmd = [
        sys.executable, "-m", "mlx_lm.lora",
        "--model", model,
        "--train",
        "--data", str(MLX_DATA),
        "--iters", str(iters),
        "--batch-size", "1",
        "--grad-accumulation-steps", "2",
        "--num-layers", "8",
        "--learning-rate", "1e-4",
        "--adapter-path", str(ADAPTER_OUT),
        "--save-every", "100",
        "--steps-per-eval", "50",
        "--steps-per-report", "10",
        "--max-seq-length", "3072",
        "--grad-checkpoint",
        "--seed", "42",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Adapter saved: {ADAPTER_OUT}")


# ──────────────────────────────────────────────────────────────────────
# 3. Fuse adapter into a single MLX model.
# ──────────────────────────────────────────────────────────────────────

def fuse(model: str = BASE_MODEL) -> None:
    _ensure_mlx_lm()
    if not ADAPTER_OUT.exists() or not any(ADAPTER_OUT.iterdir()):
        sys.exit(
            f"Adapter not found at {ADAPTER_OUT}.\n"
            "Run training first:  python finetune/train_mlx.py"
        )
    if FUSED_OUT.exists():
        shutil.rmtree(FUSED_OUT)
    cmd = [
        sys.executable, "-m", "mlx_lm.fuse",
        "--model", model,
        "--adapter-path", str(ADAPTER_OUT),
        "--save-path", str(FUSED_OUT),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Fused model: {FUSED_OUT}")


# ──────────────────────────────────────────────────────────────────────
# 4. Convert fused model to GGUF for Ollama.
# ──────────────────────────────────────────────────────────────────────

def to_gguf() -> None:
    if not FUSED_OUT.exists():
        sys.exit("Fused model not found. Run with --fuse first.")
    GGUF_OUT.mkdir(exist_ok=True)
    print(
        "MLX does not export GGUF directly. Use llama.cpp convert script:\n"
        "  git clone https://github.com/ggerganov/llama.cpp\n"
        "  cd llama.cpp && pip install -r requirements.txt\n"
        f"  python convert_hf_to_gguf.py {FUSED_OUT} --outfile {GGUF_OUT}/serena.gguf\n"
        "  ./build/bin/llama-quantize "
        f"{GGUF_OUT}/serena.gguf {GGUF_OUT}/serena.Q4_K_M.gguf Q4_K_M\n"
        "Then update finetune/Modelfile to point at the .gguf file and run:\n"
        "  ollama create serena-pass1 -f finetune/Modelfile"
    )


# ──────────────────────────────────────────────────────────────────────
# 5. CLI.
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--convert", action="store_true", help="Convert data only")
    parser.add_argument("--fuse", action="store_true", help="Fuse adapter into model")
    parser.add_argument("--gguf", action="store_true", help="Print GGUF conversion steps")
    parser.add_argument("--model", default=BASE_MODEL, help="HF/MLX model id")
    parser.add_argument("--iters", type=int, default=600, help="Training iterations")
    args = parser.parse_args()

    if args.gguf:
        to_gguf()
        return
    if args.fuse:
        fuse(args.model)
        return

    print("Step 1/2: convert dataset to JSONL")
    convert_to_jsonl()

    if args.convert:
        return

    print("Step 2/2: run mlx_lm.lora training")
    run_training(args.model, args.iters)

    print(
        "\nNext:\n"
        f"  python finetune/train_mlx.py --fuse   # merge adapter\n"
        f"  python finetune/train_mlx.py --gguf   # GGUF conversion steps\n"
    )


if __name__ == "__main__":
    main()
