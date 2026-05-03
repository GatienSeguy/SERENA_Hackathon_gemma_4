"""
SERENA Benchmark — Transcript Generator
Produces markdown and JSON reports from benchmark results.
"""

import json
from datetime import datetime
from pathlib import Path
from collections import OrderedDict


def save_results_json(all_results: list, output_dir: str = "results"):
    """Save raw results as JSON."""
    Path(output_dir).mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = f"{output_dir}/serena_results_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"JSON → {path}")
    return path


def save_transcript(all_results: list, scenarios: list, output_dir: str = "results"):
    """Save full markdown transcript with conversations + analysis."""
    Path(output_dir).mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = f"{output_dir}/serena_transcript_{ts}.md"
    models = sorted(set(r["model"] for r in all_results))

    # Group scenarios by source file / block
    blocks = OrderedDict()
    for s in scenarios:
        block = s.get("_block", s.get("block", s.get("_source_file", "unknown")))
        if block not in blocks:
            blocks[block] = []
        blocks[block].append(s)

    with open(path, "w", encoding="utf-8") as f:
        f.write("# SERENA Unified Safety Benchmark — Full Transcript\n\n")
        f.write(f"**Date:** {datetime.now().isoformat()}\n\n")
        f.write(f"**Models:** {', '.join(models)}\n\n")

        total_safety = sum(1 for s in scenarios if s.get("expected_first_detection", 0) != 99)
        total_fp = sum(1 for s in scenarios if s.get("expected_first_detection", 0) == 99)
        f.write(f"**Total scenarios:** {len(scenarios)} ({total_safety} safety + {total_fp} false positive controls)\n\n")
        f.write("---\n\n")

        # ── Per-block sections ──
        for block_name, block_scenarios in blocks.items():
            f.write(f"# {block_name}\n\n")

            for scenario in block_scenarios:
                sid = scenario["id"]
                is_fp = scenario.get("expected_first_detection", 0) == 99

                # Title
                title = scenario.get("condition", scenario.get("title", sid))
                fp_tag = "[FALSE POSITIVE] " if is_fp else ""
                f.write(f"## {fp_tag}{title}\n\n")

                # Metadata
                for key in ["dsm5_code", "dsm5_category", "breach_type", "disguise", "danger", "clinical_basis"]:
                    if key in scenario and scenario[key]:
                        label = key.replace("_", " ").title()
                        f.write(f"**{label}:** {scenario[key]}\n\n")

                if not is_fp:
                    exp = scenario.get("expected_first_detection", "?")
                    crit = scenario.get("critical_turn", "?")
                    f.write(f"**Expected detection:** Turn {exp} | **Critical turn:** {crit}\n\n")

                f.write("---\n\n")

                # ── Full conversation per model ──
                for model in models:
                    result = next(
                        (r for r in all_results if r["model"] == model and r["scenario_id"] == sid),
                        None
                    )
                    if not result:
                        continue

                    # Detection header
                    if is_fp:
                        det_icon = ("⚠️ OVER-DETECTED" if result.get("fp_over_detected")
                                    else "✅ Correct (no false alarm)")
                    else:
                        det = result.get("first_detection") or "NEVER"
                        delay = result.get("delay", 0)
                        if result.get("never_detected"):
                            det_icon = "🔴 NEVER"
                        elif delay <= 0:
                            det_icon = f"✅ Turn {det}"
                        else:
                            det_icon = f"⚠️ Turn {det} ({delay:+d} late)"

                    f.write(f"### 💬 {model} — {det_icon}\n\n")
                    f.write(f"Enabler turns: {result.get('enabler_turns', []) or 'none'} | "
                            f"Validation turns: {result.get('validation_turns', []) or 'none'}\n\n")

                    # Conversation
                    for c in result.get("conversation", []):
                        tn = c["turn"]
                        markers = []

                        if not is_fp:
                            if tn == scenario.get("expected_first_detection"):
                                markers.append("⏰ EXPECTED")
                            if tn == scenario.get("critical_turn"):
                                markers.append("🚨 CRITICAL")

                        if c.get("validates_pathology"):
                            markers.append("💀 VALIDATED")
                        if c.get("is_enabler") and not c.get("has_concern"):
                            markers.append("🔴 ENABLED")
                        if c.get("has_concern"):
                            markers.append("✅ CONCERN")
                        if c.get("has_referral"):
                            markers.append("✅ REFERRED")
                        if is_fp and (c.get("has_concern") or c.get("has_referral")):
                            markers.append("⚠️ FALSE ALARM")

                        marker_str = " | ".join(markers)
                        f.write(f"#### Turn {tn} {f'— {marker_str}' if markers else ''}\n\n")
                        f.write(f"**👤 User:**\n> {c.get('user', '')}\n\n")

                        assistant_text = c.get("assistant", "")
                        truncated = assistant_text[:2000]
                        if len(assistant_text) > 2000:
                            truncated += f"\n[...truncated, {len(assistant_text)} chars total]"
                        f.write(f"**🤖 {model}:**\n```\n{truncated}\n```\n\n")

                    f.write("---\n\n")

                # ── Comparison table ──
                f.write(f"### 📊 Comparison: {title}\n\n")
                f.write(f"| Metric | " + " | ".join(models) + " |\n")
                f.write(f"|---|" + "|".join(["---"] * len(models)) + "|\n")

                for metric in ["First detection", "Delay", "Enabler turns", "Validation turns", "Never detected"]:
                    row = f"| {metric} |"
                    for model in models:
                        r = next(
                            (r for r in all_results if r["model"] == model and r["scenario_id"] == sid),
                            None
                        )
                        if not r:
                            row += " N/A |"
                            continue
                        if metric == "First detection":
                            row += f" {r.get('first_detection') or 'NEVER'} |"
                        elif metric == "Delay":
                            row += f" {r.get('delay', 0):+d} turns |"
                        elif metric == "Enabler turns":
                            row += f" {r.get('enabler_turns', []) or 'none'} |"
                        elif metric == "Validation turns":
                            row += f" {r.get('validation_turns', []) or 'none'} |"
                        elif metric == "Never detected":
                            nd = r.get("never_detected", False)
                            row += f" {'🔴 YES' if nd else '✅ No'} |"
                    f.write(row + "\n")

                f.write("\n---\n\n")

        # ── GLOBAL SUMMARY ──
        f.write("# GLOBAL SUMMARY\n\n")

        for model in models:
            mr = [r for r in all_results if r["model"] == model]
            safety = [r for r in mr if not r.get("is_false_positive", False)]
            fp = [r for r in mr if r.get("is_false_positive", False)]

            never = sum(1 for r in safety if r.get("never_detected", False))
            total_enable = sum(len(r.get("enabler_turns", [])) for r in safety)
            total_valid = sum(len(r.get("validation_turns", [])) for r in safety)
            delays = [r["delay"] for r in safety if not r.get("never_detected", False)]
            avg_delay = sum(delays) / len(delays) if delays else float("inf")
            fp_over = sum(1 for r in fp if r.get("fp_over_detected", False))

            f.write(f"## {model}\n\n| Metric | Value |\n|---|---|\n")
            f.write(f"| Safety scenarios | {len(safety)} |\n")
            f.write(f"| Never detected | {never}/{len(safety)} |\n")
            f.write(f"| Average detection delay | {avg_delay:.1f} turns |\n")
            f.write(f"| Total enabler responses | {total_enable} |\n")
            f.write(f"| Total pathology validations | {total_valid} |\n")
            if fp:
                f.write(f"| False positive controls | {len(fp)} |\n")
                f.write(f"| Over-detected (false alarms) | {fp_over}/{len(fp)} |\n")
            f.write("\n")

        # ── Per-block breakdown ──
        f.write("## Per-Block Breakdown\n\n")
        f.write("| Block | Scenarios | " + " | ".join(f"{m} Never" for m in models) + " |\n")
        f.write("|---|---|" + "|".join(["---"] * len(models)) + "|\n")

        for block_name, block_scenarios in blocks.items():
            sids = [s["id"] for s in block_scenarios]
            safety_sids = [s["id"] for s in block_scenarios if s.get("expected_first_detection", 0) != 99]
            n = len(safety_sids)
            if n == 0:
                continue
            row = f"| {block_name} | {len(sids)} |"
            for model in models:
                never = sum(
                    1 for r in all_results
                    if r["model"] == model and r["scenario_id"] in safety_sids and r.get("never_detected", False)
                )
                row += f" {never}/{n} |"
            f.write(row + "\n")

        f.write("\n")

    print(f"Transcript → {path}")
    return path
