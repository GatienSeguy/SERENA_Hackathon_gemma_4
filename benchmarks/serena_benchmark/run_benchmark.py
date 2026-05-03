#!/usr/bin/env python3
"""
SERENA Unified Safety Benchmark
================================
Single runner for all SERENA safety benchmarks.

Scenarios are loaded from external JSON files in the scenarios/ directory.
Each JSON file contains a block of related scenarios.

Usage:
    # Run all scenarios on all models
    python run_benchmark.py

    # Run a specific scenario file
    python run_benchmark.py --file scenarios/01_breach.json

    # Run a specific scenario by ID
    python run_benchmark.py --id mania_startup

    # Run only on one model
    python run_benchmark.py --model gemma4:e2b

    # Run only false positive controls
    python run_benchmark.py --fp-only

    # Dry run (list scenarios without running)
    python run_benchmark.py --dry-run

    # Custom config
    python run_benchmark.py --config my_config.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import ollama
except ImportError:
    os.system("pip install ollama --break-system-packages")
    import ollama

from engine import load_config, analyze_response, get_turn_icon, compute_scenario_metrics, load_scenarios, print_summary
from transcript import save_results_json, save_transcript


def run_scenario(model: str, scenario: dict, config: dict) -> dict:
    """Run a single multi-turn scenario against a model."""
    sid = scenario["id"]
    user_turns = [t for t in scenario["turns"] if t["role"] == "user"]
    total = len(user_turns)
    is_fp = scenario.get("expected_first_detection", 0) == 99

    # Header
    block = scenario.get("_block", scenario.get("block", ""))
    condition = scenario.get("condition", scenario.get("title", sid))
    fp_label = " [FALSE POSITIVE]" if is_fp else ""
    print(f"\n  ┌─ [{block}] {condition}{fp_label} ({total} turns)")

    messages = []
    conversation = []
    ollama_opts = config.get("ollama_options", {"temperature": 0.0, "num_predict": 1024})

    for i, turn in enumerate(user_turns):
        tn = i + 1
        print(f"  │ Turn {tn}/{total}: ", end="", flush=True)

        messages.append({"role": "user", "content": turn["content"]})

        try:
            start = time.time()
            resp = ollama.chat(
                model=model,
                messages=messages,
                options=ollama_opts,
            )
            elapsed = time.time() - start
            response_text = resp["message"]["content"]
            messages.append({"role": "assistant", "content": response_text})

            analysis = analyze_response(response_text, config)
            icon = get_turn_icon(analysis, is_fp)

            ref = "ref✓" if analysis["has_referral"] else "ref✗"
            conc = "conc✓" if analysis["has_concern"] else "conc✗"
            print(f"{icon} {ref} {conc} ({elapsed:.1f}s)")

            conversation.append({
                "turn": tn,
                "user": turn["content"],
                "assistant": response_text,
                "time_s": round(elapsed, 2),
                **analysis,
            })

        except Exception as e:
            print(f"ERROR: {e}")
            messages.append({"role": "assistant", "content": f"[ERROR: {e}]"})
            conversation.append({
                "turn": tn,
                "user": turn["content"],
                "assistant": f"ERROR: {e}",
                "time_s": None,
                "has_concern": False,
                "has_referral": False,
                "is_enabler": False,
                "validates_pathology": False,
            })

        time.sleep(0.3)

    # Compute metrics
    metrics = compute_scenario_metrics(conversation, scenario)

    # Print result
    if is_fp:
        status = "⚠️ OVER-DETECTED" if metrics["fp_over_detected"] else "✅ Correct (no alert)"
        print(f"  │ False positive: {status}")
    else:
        det = metrics["first_detection"] or "NEVER"
        exp = metrics["expected_detection"]
        delay = metrics["delay"]
        print(f"  │ Detection: turn {det} (expected: {exp}, delay: {delay:+d})")
        print(f"  │ Enabler turns: {metrics['enabler_turns'] or 'none'}")
        print(f"  │ Validation turns: {metrics['validation_turns'] or 'none'}")

    d = metrics["delay"]
    ok = (is_fp and not metrics["fp_over_detected"]) or (not is_fp and d <= 0)
    warn = not is_fp and 0 < d <= 2
    print(f"  └─ {'✅' if ok else '⚠️' if warn else '🔴'}")

    return {
        "model": model,
        "scenario_id": sid,
        "block": scenario.get("_block", scenario.get("block", "")),
        "condition": scenario.get("condition", scenario.get("title", "")),
        "dsm5_code": scenario.get("dsm5_code", ""),
        "dsm5_category": scenario.get("dsm5_category", ""),
        "breach_type": scenario.get("breach_type", ""),
        "disguise": scenario.get("disguise", ""),
        "danger": scenario.get("danger", ""),
        "total_turns": total,
        "conversation": conversation,
        **metrics,
    }


def main():
    parser = argparse.ArgumentParser(description="SERENA Unified Safety Benchmark")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument("--file", help="Run only scenarios from this JSON file")
    parser.add_argument("--id", help="Run only the scenario with this ID")
    parser.add_argument("--model", help="Run only on this model")
    parser.add_argument("--fp-only", action="store_true", help="Run only false positive controls")
    parser.add_argument("--no-fp", action="store_true", help="Skip false positive controls")
    parser.add_argument("--dry-run", action="store_true", help="List scenarios without running")
    parser.add_argument("--scenarios-dir", default="scenarios", help="Scenarios directory")
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Load scenarios
    if args.file:
        # Load from specific file
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            scenarios = data
        elif isinstance(data, dict) and "scenarios" in data:
            for s in data["scenarios"]:
                s["_block"] = data.get("block", Path(args.file).stem)
            scenarios = data["scenarios"]
        else:
            print(f"Unknown format in {args.file}")
            sys.exit(1)
    else:
        scenarios = load_scenarios(args.scenarios_dir)

    if not scenarios:
        print("No scenarios found. Add JSON files to the scenarios/ directory.")
        print("Run: python extract_scenarios.py  to extract from existing benchmarks.")
        sys.exit(1)

    # Filter
    if args.id:
        scenarios = [s for s in scenarios if s["id"] == args.id]
    if args.fp_only:
        scenarios = [s for s in scenarios if s.get("expected_first_detection", 0) == 99]
    if args.no_fp:
        scenarios = [s for s in scenarios if s.get("expected_first_detection", 0) != 99]

    # Models
    models = [args.model] if args.model else config["models"]

    # Count
    total_turns = sum(len([t for t in s["turns"] if t["role"] == "user"]) for s in scenarios)
    safety_count = sum(1 for s in scenarios if s.get("expected_first_detection", 0) != 99)
    fp_count = sum(1 for s in scenarios if s.get("expected_first_detection", 0) == 99)

    print(f"\n{'='*60}")
    print(f"  SERENA UNIFIED SAFETY BENCHMARK")
    print(f"{'='*60}")
    print(f"  Scenarios:     {len(scenarios)} ({safety_count} safety + {fp_count} false positive)")
    print(f"  User turns:    {total_turns}")
    print(f"  Models:        {', '.join(models)}")
    print(f"  Est. time:     ~{total_turns * len(models) * 25 // 60} min")
    print(f"{'='*60}")

    if args.dry_run:
        print("\n  Dry run — listing scenarios:\n")
        for i, s in enumerate(scenarios, 1):
            fp = " [FP]" if s.get("expected_first_detection", 0) == 99 else ""
            turns = len([t for t in s["turns"] if t["role"] == "user"])
            block = s.get("_block", s.get("block", ""))
            cond = s.get("condition", s.get("title", s["id"]))
            print(f"  {i:3d}. [{block}] {cond}{fp} ({turns} turns)")
        print(f"\n  Total: {len(scenarios)} scenarios, {total_turns} turns")
        return

    # Run
    all_results = []

    for model in models:
        # Check model exists
        try:
            ollama.show(model)
        except Exception:
            print(f"\n⚠ Model {model} not found. Run: ollama pull {model}")
            continue

        print(f"\n{'='*60}")
        print(f"  MODEL: {model}")
        print(f"{'='*60}")

        for scenario in scenarios:
            result = run_scenario(model, scenario, config)
            all_results.append(result)

    if not all_results:
        print("\nNo results generated.")
        return

    # Save
    output_dir = config.get("output", {}).get("results_dir", "results")
    save_results_json(all_results, output_dir)
    save_transcript(all_results, scenarios, output_dir)
    print_summary(all_results)

    print(f"\n{'='*60}")
    print(f"  DONE — {len(all_results)} results saved")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
