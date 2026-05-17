"""SERENA — Fine-tune Gemma with Unsloth LoRA for Pass 1 (Colab/Linux+NVIDIA).

Hardware:
    Unsloth requires NVIDIA / AMD / Intel GPU. Apple Silicon NOT supported.
    On Mac M-series, use finetune/train_mlx.py instead.

Colab usage:
    1. Upload finetune/train.json + finetune/val.json
    2. Paste this script in a cell, run.

Output:
    finetune/serena-lora/        — adapter weights
    finetune/serena-gguf/        — quantized GGUF for Ollama
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# ── 0. Paths ──
HERE = Path(__file__).resolve().parent
TRAIN_JSON = HERE / "train.json"
VAL_JSON = HERE / "val.json"
LORA_OUT = HERE / "serena-lora"
GGUF_OUT = HERE / "serena-gguf"
CKPT_OUT = HERE / "checkpoints"

# ── 1. Hardware guard (BEFORE importing torch — avoids OMP clash on Mac) ──
import platform  # noqa: E402

if sys.platform == "darwin" or platform.machine() == "arm64":
    sys.stderr.write(
        "ERROR: Unsloth requires NVIDIA/AMD/Intel GPU. "
        "Apple Silicon not supported.\n"
        "On Mac M-series, run: python finetune/train_mlx.py\n"
    )
    sys.exit(1)


def _has_supported_gpu() -> bool:
    try:
        import torch
        if torch.cuda.is_available():
            return True
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return True
    except Exception:
        pass
    return False


if not _has_supported_gpu():
    sys.stderr.write(
        "ERROR: No supported GPU detected. "
        "Run on Google Colab (free T4) or NVIDIA host.\n"
    )
    sys.exit(1)

# ── 2. Install Unsloth if missing (Colab convenience) ──
try:
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import get_chat_template
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "unsloth"], check=True)
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import get_chat_template

import torch  # noqa: E402
from datasets import Dataset  # noqa: E402
from transformers import TrainingArguments  # noqa: E402
from trl import SFTTrainer  # noqa: E402

# ── 3. Base model ──
# Gemma 4 E2B not yet on HF as of this script. Adjust MODEL_NAME if needed.
MODEL_NAME = "unsloth/gemma-2-2b-it-bnb-4bit"
MAX_SEQ_LEN = 4096

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LEN,
    load_in_4bit=True,
    dtype=None,
)

# ── 4. LoRA config ──
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=16,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

# ── 5. Load dataset ──
train_data = json.loads(TRAIN_JSON.read_text(encoding="utf-8"))
val_data = json.loads(VAL_JSON.read_text(encoding="utf-8"))
print(f"Train: {len(train_data)}  Val: {len(val_data)}")

# ── 6. Apply chat template ──
tokenizer = get_chat_template(tokenizer, chat_template="gemma")


def format_example(example: dict) -> dict:
    text = tokenizer.apply_chat_template(
        example["conversations"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}


train_dataset = Dataset.from_list(train_data).map(format_example)
val_dataset = Dataset.from_list(val_data).map(format_example)

# ── 7. Train ──
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_dataset,
    eval_dataset=val_dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LEN,
    args=TrainingArguments(
        output_dir=str(CKPT_OUT),
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=3,
        learning_rate=2e-4,
        warmup_steps=10,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=50,
        seed=42,
        report_to="none",
    ),
)

print("Training start...")
trainer.train()

# ── 8. Save LoRA ──
model.save_pretrained(str(LORA_OUT))
tokenizer.save_pretrained(str(LORA_OUT))
print(f"LoRA saved: {LORA_OUT}")

# ── 9. Export GGUF for Ollama ──
model.save_pretrained_gguf(
    str(GGUF_OUT),
    tokenizer,
    quantization_method="q4_k_m",
)
print(f"GGUF: {GGUF_OUT}")
print("Next:  ollama create serena-pass1 -f finetune/Modelfile")
