#!/usr/bin/env python3
"""Train a JamBox vibe parser/draft adapter using LoRA or QLoRA."""

from __future__ import annotations

import argparse
import json
import os

import yaml


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))


def _require_training_deps():
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:
        raise SystemExit(
            "Missing training dependencies. Install transformers, datasets, peft, bitsandbytes, and torch before running train_lora.py."
        ) from exc
    return {
        "torch": torch,
        "Dataset": Dataset,
        "LoraConfig": LoraConfig,
        "get_peft_model": get_peft_model,
        "prepare_model_for_kbit_training": prepare_model_for_kbit_training,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "BitsAndBytesConfig": BitsAndBytesConfig,
        "DataCollatorForLanguageModeling": DataCollatorForLanguageModeling,
        "Trainer": Trainer,
        "TrainingArguments": TrainingArguments,
    }


def _load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_rows(path):
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _resolve_repo_path(path):
    if os.path.isabs(path):
        return path
    return os.path.join(REPO_DIR, path)


def _format_example(row):
    return (
        "You are the JamBox vibe assistant.\n"
        f"Task: {row['task']}\n"
        f"Input: {json.dumps(row['input'], sort_keys=True)}\n"
        f"Output: {json.dumps(row['output'], sort_keys=True)}"
    )


def main():
    parser = argparse.ArgumentParser(description="Train a JamBox LoRA adapter")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    deps = _require_training_deps()
    config = _load_config(args.config)
    dataset_path = _resolve_repo_path(config["dataset_path"])
    output_dir = _resolve_repo_path(config["output_dir"])
    rows = _load_rows(dataset_path)
    if not rows:
        raise SystemExit(f"No training rows found in {dataset_path}")

    dataset = deps["Dataset"].from_dict({"text": [_format_example(row) for row in rows]})
    tokenizer = deps["AutoTokenizer"].from_pretrained(config["base_model"], use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant_cfg = None
    if config.get("quantization", {}).get("load_in_4bit"):
        quant_cfg = deps["BitsAndBytesConfig"](
            load_in_4bit=True,
            bnb_4bit_compute_dtype=getattr(deps["torch"], config["quantization"].get("bnb_4bit_compute_dtype", "float16")),
        )

    model = deps["AutoModelForCausalLM"].from_pretrained(
        config["base_model"],
        quantization_config=quant_cfg,
        device_map="auto",
    )
    if quant_cfg is not None:
        model = deps["prepare_model_for_kbit_training"](model)

    lora_cfg = deps["LoraConfig"](
        r=config["lora"]["r"],
        lora_alpha=config["lora"]["alpha"],
        lora_dropout=config["lora"]["dropout"],
        target_modules=config["lora"]["target_modules"],
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = deps["get_peft_model"](model, lora_cfg)

    def tokenize(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=config.get("max_seq_length", 2048),
            padding="max_length",
        )

    tokenized = dataset.map(tokenize, batched=True, remove_columns=["text"])
    training_args = deps["TrainingArguments"](
        output_dir=output_dir,
        learning_rate=config.get("learning_rate", 2e-4),
        num_train_epochs=config.get("num_train_epochs", 3),
        per_device_train_batch_size=config.get("per_device_train_batch_size", 1),
        gradient_accumulation_steps=config.get("gradient_accumulation_steps", 8),
        logging_steps=config.get("logging_steps", 10),
        save_steps=config.get("save_steps", 100),
        bf16=False,
        fp16=True,
        report_to=[],
    )
    trainer = deps["Trainer"](
        model=model,
        args=training_args,
        train_dataset=tokenized,
        data_collator=deps["DataCollatorForLanguageModeling"](tokenizer=tokenizer, mlm=False),
    )
    trainer.train()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)


if __name__ == "__main__":
    main()
