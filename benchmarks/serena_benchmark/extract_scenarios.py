#!/usr/bin/env python3
"""
Extract scenarios from existing SERENA benchmark Python files
into clean JSON files in the scenarios/ directory.

Usage:
    python extract_scenarios.py /path/to/Hackathon_gemma_4/

This reads the Python source files, extracts the scenario data structures,
and writes them as clean JSON files organized by block.
"""

import ast
import json
import os
import re
import sys
from pathlib import Path


def extract_list_from_python(filepath: str, var_names: list[str]) -> list[dict]:
    """
    Extract a list of dicts from a Python file by finding the variable assignment.
    Uses regex + ast.literal_eval for robustness.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(filepath, "r", encoding="latin-1") as f:
            content = f.read()

    for var_name in var_names:
        # Find the variable assignment
        # Match: VAR_NAME = [ ... ]
        pattern = rf'{var_name}\s*=\s*\['
        match = re.search(pattern, content)
        if not match:
            continue

        # Find the matching closing bracket
        start = match.start()
        bracket_start = content.index('[', start)

        depth = 0
        i = bracket_start
        while i < len(content):
            if content[i] == '[':
                depth += 1
            elif content[i] == ']':
                depth -= 1
                if depth == 0:
                    break
            i += 1

        list_str = content[bracket_start:i+1]

        # Clean up Python-specific syntax for JSON compatibility
        # Replace single quotes with double quotes (carefully)
        # Replace True/False/None
        try:
            result = ast.literal_eval(list_str)
            if isinstance(result, list):
                return result
        except (SyntaxError, ValueError) as e:
            print(f"  ⚠ ast.literal_eval failed for {var_name} in {filepath}: {e}")
            continue

    return []


def normalize_scenario(s: dict) -> dict:
    """Normalize a scenario to the unified format."""
    normalized = {
        "id": s.get("id", "unknown"),
        "condition": s.get("condition", s.get("title", "")),
        "disguise": s.get("disguise", ""),
        "danger": s.get("danger", ""),
        "expected_first_detection": s.get("expected_first_detection", s.get("expected_detection", 1)),
        "critical_turn": s.get("critical_turn", 1),
        "turns": s.get("turns", []),
    }

    # Copy optional metadata fields
    for key in ["dsm5_category", "dsm5_code", "clinical_basis",
                 "breach_type", "block", "title"]:
        if key in s:
            normalized[key] = s[key]

    return normalized


def process_source_dir(source_dir: str, output_dir: str = "scenarios"):
    """Process all Python files in the source directory."""
    source = Path(source_dir)
    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    total = 0

    # ── 1. Multi-turn benchmark ──
    multi = source / "multi_bench" / "multi_bench.py"
    if multi.exists():
        scenarios = extract_list_from_python(str(multi), ["SCENARIOS", "scenarios"])
        if scenarios:
            normalized = [normalize_scenario(s) for s in scenarios]
            save_block(normalized, out / "01_multiturn.json",
                       "Multi-Turn Benchmark", "Original multi-turn safety conversations")
            total += len(normalized)
            print(f"  ✅ 01_multiturn.json: {len(normalized)} scenarios")

    # ── 2. Breach benchmark ──
    for name in ["bench.py", "breach.py"]:
        breach = source / "Benchmark_poussé" / name
        if breach.exists():
            scenarios = extract_list_from_python(str(breach), ["SCENARIOS", "scenarios"])
            if scenarios:
                normalized = [normalize_scenario(s) for s in scenarios]
                save_block(normalized, out / "02_breach.json",
                           "Breach Exploitation", "Targeted exploitation of identified safety breaches")
                total += len(normalized)
                print(f"  ✅ 02_breach.json: {len(normalized)} scenarios")
                break

    # ── 3. Extended scenarios ──
    for name in ["exteded.py", "extended.py"]:
        ext = source / "Benchmark_poussé" / name
        if ext.exists():
            scenarios = extract_list_from_python(str(ext), [
                "EXTENDED_SCENARIOS", "extended_scenarios", "SCENARIOS", "scenarios"
            ])
            if scenarios:
                normalized = [normalize_scenario(s) for s in scenarios]
                save_block(normalized, out / "03_extended.json",
                           "Extended Scenarios", "Additional scenario coverage")
                total += len(normalized)
                print(f"  ✅ 03_extended.json: {len(normalized)} scenarios")
                break

    # ── 4. DSM-5 Phase 1 ──
    for name in ["DSM.py", "dsm.py", "dsm5.py"]:
        dsm = source / "bench_DSM5" / name
        if dsm.exists():
            scenarios = extract_list_from_python(str(dsm), [
                "DSM5_SCENARIOS", "dsm5_scenarios", "SCENARIOS", "scenarios"
            ])
            if scenarios:
                # Group by DSM-5 category
                categories = {}
                for s in scenarios:
                    cat = s.get("dsm5_category", "Other")
                    if cat not in categories:
                        categories[cat] = []
                    categories[cat].append(normalize_scenario(s))

                idx = 4
                for cat_name, cat_scenarios in categories.items():
                    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', cat_name).lower().strip('_')
                    filename = f"{idx:02d}_dsm5_{safe_name}.json"
                    save_block(cat_scenarios, out / filename,
                               f"DSM-5: {cat_name}", f"DSM-5 category: {cat_name}")
                    total += len(cat_scenarios)
                    print(f"  ✅ {filename}: {len(cat_scenarios)} scenarios")
                    idx += 1
                break

    # ── 5. DSM-5 Phase 2 ──
    for name in ["SQM2.py", "sqm2.py", "dsm5_phase2.py"]:
        dsm2 = source / "bench_DSM5" / name
        if dsm2.exists():
            scenarios = extract_list_from_python(str(dsm2), [
                "SCENARIOS", "scenarios", "DSM5_SCENARIOS"
            ])
            if scenarios:
                # Group by block
                blocks = {}
                for s in scenarios:
                    block = s.get("block", "Other")
                    if block not in blocks:
                        blocks[block] = []
                    blocks[block].append(normalize_scenario(s))

                idx = 20
                for block_name, block_scenarios in blocks.items():
                    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', block_name).lower().strip('_')
                    # Limit filename length
                    safe_name = safe_name[:40]
                    filename = f"{idx:02d}_{safe_name}.json"
                    save_block(block_scenarios, out / filename,
                               block_name, f"Phase 2: {block_name}")
                    total += len(block_scenarios)
                    print(f"  ✅ {filename}: {len(block_scenarios)} scenarios")
                    idx += 1
                break

    print(f"\n  Total: {total} scenarios extracted → {output_dir}/")
    return total


def save_block(scenarios: list, filepath: Path, block_name: str, description: str):
    """Save a block of scenarios to a JSON file."""
    data = {
        "block": block_name,
        "description": description,
        "count": len(scenarios),
        "scenarios": scenarios
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    if len(sys.argv) < 2:
        # Try default path
        default_paths = [
            ".",
            "../Hackathon_gemma_4",
            "Hackathon_gemma_4",
        ]
        source_dir = None
        for p in default_paths:
            if (Path(p) / "bench_DSM5").exists() or (Path(p) / "multi_bench").exists():
                source_dir = p
                break

        if not source_dir:
            print("Usage: python extract_scenarios.py /path/to/Hackathon_gemma_4/")
            print("       The directory should contain bench_DSM5/, multi_bench/, etc.")
            sys.exit(1)
    else:
        source_dir = sys.argv[1]

    print(f"\n{'='*60}")
    print(f"  SERENA — Extracting scenarios from {source_dir}")
    print(f"{'='*60}\n")

    total = process_source_dir(source_dir, "scenarios")

    if total == 0:
        print("\n  ⚠ No scenarios extracted. Check that the Python files exist.")
        print("  Expected structure:")
        print("    Hackathon_gemma_4/")
        print("    ├── multi_bench/multi_bench.py")
        print("    ├── Benchmark_poussé/bench.py")
        print("    ├── Benchmark_poussé/exteded.py")
        print("    ├── bench_DSM5/DSM.py")
        print("    └── bench_DSM5/SQM2.py")
    else:
        print(f"\n  ✅ Done! Run the benchmark with:")
        print(f"     python run_benchmark.py")
        print(f"     python run_benchmark.py --dry-run  (to list scenarios)")


if __name__ == "__main__":
    main()
