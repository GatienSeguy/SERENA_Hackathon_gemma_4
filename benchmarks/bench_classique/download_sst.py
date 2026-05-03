"""
Download SimpleSafetyTests (SST) benchmark dataset.
Source: Vidgen et al. (2024) - "SimpleSafetyTests: a Test Suite for 
Identifying Critical Safety Risks in Large Language Models"

Paper: https://arxiv.org/abs/2311.08370
Repo: https://github.com/bertiev/SimpleSafetyTests
License: CC BY-NC 4.0
"""

import os
import urllib.request
import csv

SST_URL = "https://raw.githubusercontent.com/bertiev/SimpleSafetyTests/main/SimpleSafetyTests%20-%20test%20cases.csv"
OUTPUT_FILE = "sst_prompts.csv"


def download_sst():
    if os.path.exists(OUTPUT_FILE):
        print(f"{OUTPUT_FILE} already exists. Delete it to re-download.")
        return

    print(f"Downloading SimpleSafetyTests from GitHub...")
    try:
        urllib.request.urlretrieve(SST_URL, OUTPUT_FILE)
        print(f"Saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Download failed: {e}")
        print("You can manually download from:")
        print("  https://github.com/bertiev/SimpleSafetyTests")
        return

    # Quick validation
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        print(f"Loaded {len(rows) - 1} prompts (header + {len(rows)-1} test cases)")

    # Show categories
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        categories = set()
        for row in reader:
            cat = row.get("harm_area", row.get("Harm_area", "unknown"))
            categories.add(cat)
        print(f"Categories: {', '.join(sorted(categories))}")


if __name__ == "__main__":
    download_sst()