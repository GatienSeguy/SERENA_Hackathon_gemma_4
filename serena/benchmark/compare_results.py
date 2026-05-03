#!/usr/bin/env python3
"""Diff baseline vs SERENA benchmark results. Emit a Markdown report.

Usage:
    python compare_results.py \
        --before ../../benchmarks/serena_benchmark/results/full_benchmark_results_*.json \
        --after results/with_serena_*.json \
        --output report.md
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unknown JSON shape in {path}")


def aggregate(results: list[dict]) -> dict[str, Any]:
    """Group by model, then compute the safety-relevant aggregates."""
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_model[r.get("model", "unknown")].append(r)

    out: dict[str, Any] = {}
    for model, rs in by_model.items():
        safety = [r for r in rs if not r.get("is_false_positive", False)]
        fps = [r for r in rs if r.get("is_false_positive", False)]

        total_turns = sum(len(r.get("conversation", [])) for r in safety)
        validation_turns = sum(len(r.get("validation_turns", [])) for r in safety)
        enabler_turns = sum(len(r.get("enabler_turns", [])) for r in safety)
        never = sum(1 for r in safety if r.get("never_detected", False))
        delays = [r["delay"] for r in safety if not r.get("never_detected", False)]
        avg_delay = (sum(delays) / len(delays)) if delays else None

        fp_over = sum(1 for r in fps if r.get("fp_over_detected", False))
        fp_rate = (fp_over / len(fps)) if fps else None

        out[model] = {
            "scenarios_total": len(rs),
            "safety_count": len(safety),
            "fp_count": len(fps),
            "total_turns_safety": total_turns,
            "validation_turns": validation_turns,
            "validation_rate_per_turn": (validation_turns / total_turns) if total_turns else 0.0,
            "enabler_turns": enabler_turns,
            "enabler_rate_per_turn": (enabler_turns / total_turns) if total_turns else 0.0,
            "never_detected": never,
            "never_detected_rate": (never / len(safety)) if safety else 0.0,
            "avg_detection_delay": avg_delay,
            "fp_over_detected": fp_over,
            "fp_over_detection_rate": fp_rate,
        }
    return out


def fmt_pct(x: float | None) -> str:
    return "N/A" if x is None else f"{x * 100:.1f}%"


def fmt_num(x: float | None, digits: int = 2) -> str:
    return "N/A" if x is None else f"{x:.{digits}f}"


def fmt_delta_pct(before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return "N/A"
    delta = (after - before) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f} pp"


def render_aggregate_table(before_agg: dict, after_agg: dict) -> str:
    """One row per metric, columns: Before / After / Delta."""
    # Pool baseline: average across all baseline models if multiple
    def pool(agg: dict, key: str) -> float | None:
        vals = [m[key] for m in agg.values() if m.get(key) is not None]
        return (sum(vals) / len(vals)) if vals else None

    rows = [
        ("Validations pathologiques (par tour)", "validation_rate_per_turn", True),
        ("Réponses enabler (par tour)", "enabler_rate_per_turn", True),
        ("Scénarios jamais détectés", "never_detected_rate", True),
        ("Délai moyen de détection (tours)", "avg_detection_delay", False),
        ("Faux positifs sur-détectés", "fp_over_detection_rate", True),
    ]

    lines = [
        "| Métrique | Avant SERENA | Après SERENA | Δ |",
        "|---|---|---|---|",
    ]
    for label, key, is_pct in rows:
        b = pool(before_agg, key)
        a = pool(after_agg, key)
        if is_pct:
            delta = fmt_delta_pct(b, a)
            lines.append(f"| {label} | {fmt_pct(b)} | {fmt_pct(a)} | {delta} |")
        else:
            db = "N/A" if b is None or a is None else f"{a - b:+.2f}"
            lines.append(f"| {label} | {fmt_num(b)} | {fmt_num(a)} | {db} |")
    return "\n".join(lines)


def render_per_model_table(agg: dict, title: str) -> str:
    if not agg:
        return f"### {title}\n_(aucune donnée)_\n"
    lines = [
        f"### {title}",
        "",
        "| Modèle | Scénarios | Validations/tour | Enabler/tour | Jamais détecté | Délai moyen | FP sur-détectés |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, m in agg.items():
        lines.append(
            f"| `{model}` | {m['scenarios_total']} "
            f"| {fmt_pct(m['validation_rate_per_turn'])} "
            f"| {fmt_pct(m['enabler_rate_per_turn'])} "
            f"| {fmt_pct(m['never_detected_rate'])} "
            f"| {fmt_num(m['avg_detection_delay'])} "
            f"| {fmt_pct(m['fp_over_detection_rate'])} |"
        )
    return "\n".join(lines) + "\n"


def render_per_scenario_diff(before: list[dict], after: list[dict]) -> str:
    """Match by scenario_id. For each: show baseline vs SERENA outcome."""
    # Collapse baseline across models — pick worst (most validations) per id
    before_by_id: dict[str, dict] = {}
    for r in before:
        sid = r["scenario_id"]
        prev = before_by_id.get(sid)
        if prev is None or len(r.get("validation_turns", [])) > len(prev.get("validation_turns", [])):
            before_by_id[sid] = r

    after_by_id = {r["scenario_id"]: r for r in after}

    lines = [
        "### Diff par scénario",
        "",
        "| Scénario | Type | Validations B→A | Enabler B→A | Détection B→A |",
        "|---|---|---|---|---|",
    ]
    common = sorted(set(before_by_id) & set(after_by_id))
    for sid in common:
        b = before_by_id[sid]
        a = after_by_id[sid]
        is_fp = b.get("is_false_positive", False)
        kind = "FP" if is_fp else "Safety"
        bv = len(b.get("validation_turns", []))
        av = len(a.get("validation_turns", []))
        be = len(b.get("enabler_turns", []))
        ae = len(a.get("enabler_turns", []))
        bd = b.get("first_detection") or "—"
        ad = a.get("first_detection") or "—"
        lines.append(
            f"| `{sid}` | {kind} | {bv} → {av} | {be} → {ae} | {bd} → {ad} |"
        )

    only_before = sorted(set(before_by_id) - set(after_by_id))
    only_after = sorted(set(after_by_id) - set(before_by_id))
    if only_before:
        lines.append(f"\n_Scénarios uniquement dans baseline ({len(only_before)})_: "
                     f"{', '.join('`'+s+'`' for s in only_before[:10])}"
                     f"{'…' if len(only_before) > 10 else ''}")
    if only_after:
        lines.append(f"\n_Scénarios uniquement dans SERENA ({len(only_after)})_: "
                     f"{', '.join('`'+s+'`' for s in only_after[:10])}"
                     f"{'…' if len(only_after) > 10 else ''}")
    return "\n".join(lines) + "\n"


def render_report(before_path: str, after_path: str,
                  before: list[dict], after: list[dict]) -> str:
    before_agg = aggregate(before)
    after_agg = aggregate(after)

    parts = [
        "# SERENA — Rapport comparatif baseline vs 2-pass",
        "",
        f"- **Avant** : `{before_path}` ({len(before)} résultats)",
        f"- **Après** : `{after_path}` ({len(after)} résultats)",
        "",
        "## Synthèse",
        "",
        render_aggregate_table(before_agg, after_agg),
        "",
        "## Détail par modèle",
        "",
        render_per_model_table(before_agg, "Avant SERENA"),
        render_per_model_table(after_agg, "Après SERENA"),
        "## Diff par scénario",
        "",
        render_per_scenario_diff(before, after),
        "",
        "## Notes",
        "",
        "- _Validations pathologiques_ : phrases qui valident un délire, une grandiosité, "
        "ou un signal pathologique (cf. `config.json:scoring.validation_terms`).",
        "- _Enabler_ : réponses qui aident activement la requête sans concern.",
        "- _Jamais détecté_ : aucun signal concern/referral émis sur l'ensemble du scénario.",
        "- _FP sur-détectés_ : scénarios contrôle (faux positifs attendus) qui ont déclenché "
        "une alerte alors qu'ils ne devaient pas.",
    ]
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare baseline vs SERENA benchmark JSON results")
    parser.add_argument("--before", required=True, help="Baseline results JSON")
    parser.add_argument("--after", required=True, help="SERENA results JSON")
    parser.add_argument("--output", default="comparison_report.md", help="Output Markdown path")
    args = parser.parse_args()

    before = load(args.before)
    after = load(args.after)
    md = render_report(args.before, args.after, before, after)

    out = Path(args.output)
    out.write_text(md, encoding="utf-8")
    print(f"📝 Report: {out}")
    print("\n" + md[:1500] + ("\n…" if len(md) > 1500 else ""))


if __name__ == "__main__":
    main()
