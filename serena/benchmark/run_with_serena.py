#!/usr/bin/env python3
"""Re-run SERENA benchmark scenarios THROUGH SerenaCore.

Same scoring engine (concern / referral / enabler / validation) as the
baseline `benchmarks/serena_benchmark/run_benchmark.py`, but each user turn
goes through the 2-pass SERENA pipeline instead of a raw Gemma call.

Output JSON has the SAME shape as the baseline so `compare_results.py` can
diff before/after.

Usage:
    python run_with_serena.py
    python run_with_serena.py --file 01_multiturn.json
    python run_with_serena.py --id mania_startup
    python run_with_serena.py --fp-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERENA_ROOT = HERE.parent
BENCH_ROOT = SERENA_ROOT.parent / "benchmarks" / "serena_benchmark"

# Import SERENA modules + benchmark engine
sys.path.insert(0, str(SERENA_ROOT))
sys.path.insert(0, str(BENCH_ROOT))

from serena_core import SerenaCore  # noqa: E402
from engine import (  # noqa: E402
    analyze_response,
    compute_scenario_metrics,
    get_turn_icon,
    load_config,
    load_scenarios,
    print_summary,
)


def run_scenario(scenario: dict, config: dict) -> dict:
    """Run one scenario through SerenaCore. Returns same result shape as baseline."""
    sid = scenario["id"]
    user_turns = [t for t in scenario["turns"] if t["role"] == "user"]
    total = len(user_turns)
    is_fp = scenario.get("expected_first_detection", 0) == 99

    block = scenario.get("_block", scenario.get("block", ""))
    condition = scenario.get("condition", scenario.get("title", sid))
    fp_label = " [FALSE POSITIVE]" if is_fp else ""
    print(f"\n  ┌─ [{block}] {condition}{fp_label} ({total} turns)")

    serena = SerenaCore()
    conversation: list[dict] = []

    for i, turn in enumerate(user_turns):
        tn = i + 1
        print(f"  │ Turn {tn}/{total}: ", end="", flush=True)

        try:
            start = time.time()
            result = serena.process_message(turn["content"])
            elapsed = time.time() - start

            response_text = result["response"]
            analysis = analyze_response(response_text, config)
            icon = get_turn_icon(analysis, is_fp)

            ref = "ref✓" if analysis["has_referral"] else "ref✗"
            conc = "conc✓" if analysis["has_concern"] else "conc✗"
            print(
                f"{icon} {ref} {conc} | "
                f"score={result['score']:.2f} action={result['action']} ({elapsed:.1f}s)"
            )

            conversation.append({
                "turn": tn,
                "user": turn["content"],
                "assistant": response_text,
                "time_s": round(elapsed, 2),
                "serena_score": result["score"],
                "serena_action": result["action"],
                "serena_signals": list(result["signals"].keys()),
                "serena_should_notify": result["should_notify"],
                **analysis,
            })

        except Exception as e:
            print(f"ERROR: {e}")
            conversation.append({
                "turn": tn,
                "user": turn["content"],
                "assistant": f"ERROR: {e}",
                "time_s": None,
                "serena_score": 0.0,
                "serena_action": "ERROR",
                "serena_signals": [],
                "serena_should_notify": False,
                "has_concern": False,
                "has_referral": False,
                "is_enabler": False,
                "validates_pathology": False,
            })

    metrics = compute_scenario_metrics(conversation, scenario)

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
        print(
            f"  │ SERENA final action: {serena.memory.current_action} "
            f"(score={serena.memory.cumulative_risk_score:.2f}, "
            f"signals={list(serena.memory.detected_signals.keys())})"
        )

    d = metrics["delay"]
    ok = (is_fp and not metrics["fp_over_detected"]) or (not is_fp and d <= 0)
    warn = not is_fp and 0 < d <= 2
    print(f"  └─ {'✅' if ok else '⚠️' if warn else '🔴'}")

    return {
        "model": "serena+gemma4:e2b",
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
        "serena_final_score": serena.memory.cumulative_risk_score,
        "serena_final_action": serena.memory.current_action,
        "serena_final_signals": list(serena.memory.detected_signals.keys()),
        **metrics,
    }


def save_results(results: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = output_dir / f"with_serena_{ts}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n💾 Results: {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SERENA benchmark scenarios via SerenaCore")
    parser.add_argument("--config", default=str(BENCH_ROOT / "config.json"))
    parser.add_argument("--scenarios-dir", default=str(BENCH_ROOT / "scenarios"))
    parser.add_argument("--file", help="Run only scenarios from this JSON file (path or basename)")
    parser.add_argument("--id", help="Run only the scenario with this ID")
    parser.add_argument("--fp-only", action="store_true")
    parser.add_argument("--no-fp", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default=str(HERE / "results"))
    args = parser.parse_args()

    config = load_config(args.config)

    if args.file:
        path = Path(args.file)
        if not path.is_absolute() and not path.exists():
            path = Path(args.scenarios_dir) / args.file
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            scenarios = data
        elif isinstance(data, dict) and "scenarios" in data:
            for s in data["scenarios"]:
                s["_block"] = data.get("block", path.stem)
            scenarios = data["scenarios"]
        else:
            print(f"Unknown format in {path}")
            sys.exit(1)
    else:
        scenarios = load_scenarios(args.scenarios_dir)

    if not scenarios:
        print("No scenarios found.")
        sys.exit(1)

    if args.id:
        scenarios = [s for s in scenarios if s["id"] == args.id]
    if args.fp_only:
        scenarios = [s for s in scenarios if s.get("expected_first_detection", 0) == 99]
    if args.no_fp:
        scenarios = [s for s in scenarios if s.get("expected_first_detection", 0) != 99]

    total_turns = sum(len([t for t in s["turns"] if t["role"] == "user"]) for s in scenarios)
    safety = sum(1 for s in scenarios if s.get("expected_first_detection", 0) != 99)
    fp = sum(1 for s in scenarios if s.get("expected_first_detection", 0) == 99)

    print(f"\n{'='*60}")
    print(f"  SERENA BENCHMARK — WITH SerenaCore (2-pass)")
    print(f"{'='*60}")
    print(f"  Scenarios:  {len(scenarios)} ({safety} safety + {fp} false positive)")
    print(f"  User turns: {total_turns}")
    print(f"  Pipeline:   Pass1 (gemma4:e2b) + Router + Pass2 (gemma4:e2b)")
    print(f"  Est. time:  ~{total_turns * 60 // 60} min (≈60s/turn for 2 passes)")
    print(f"{'='*60}")

    if args.dry_run:
        for i, s in enumerate(scenarios, 1):
            fp_label = " [FP]" if s.get("expected_first_detection", 0) == 99 else ""
            turns = len([t for t in s["turns"] if t["role"] == "user"])
            block = s.get("_block", s.get("block", ""))
            cond = s.get("condition", s.get("title", s["id"]))
            print(f"  {i:3d}. [{block}] {cond}{fp_label} ({turns} turns)")
        return

    all_results: list[dict] = []
    print(f"\n{'='*60}\n  RUN START\n{'='*60}")
    for scenario in scenarios:
        all_results.append(run_scenario(scenario, config))

    save_results(all_results, Path(args.output_dir))
    print_summary(all_results)
    print(f"\n{'='*60}\n  DONE — {len(all_results)} scenarios\n{'='*60}")


if __name__ == "__main__":
    main()
