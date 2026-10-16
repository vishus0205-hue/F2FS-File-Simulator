"""
Main entry point for F2FS-Inspired Flash Storage Simulator.

Usage:
    python main.py

Executes:
1. Simulator validation suite (mapping integrity, GC data preservation, no overwrite, reproducibility).
2. Experiment 1: In-Place Updates vs. Log-Structured Writes.
3. Experiment 2: Storage Utilization impact (40%, 60%, 80%, 95%).
4. Experiment 3: Uniform vs. Skewed (80/20) workloads.
5. Generates summary tables, saves CSV files, and exports Matplotlib PNG charts.
"""

import argparse
import os
import sys
from typing import Any, Dict, List

from flash import FlashDevice, PageState
from filesystem import LogStructuredFS, InPlaceFS
from metrics import MetricsTracker
from workloads import generate_workload, populate_initial_data
import experiments
import visualization


def print_banner(title: str) -> None:
    print("\n" + "=" * 78)
    print(f" {title.upper()} ")
    print("=" * 78)


def validate_simulator(seed: int = 42) -> bool:
    """
    Validates the 4 core simulator invariants:
    1. Each logical block maps to exactly one valid physical page.
    2. Garbage collection preserves all data without corruption.
    3. Flash device enforces out-of-place writes (no direct overwrite on non-free page).
    4. Execution is deterministic and reproducible under fixed seed.
    """
    print_banner("Running Simulator Validation Checks")

    # 1. 1-to-1 Mapping validation
    flash = FlashDevice(num_segments=8, pages_per_segment=16)
    fs = LogStructuredFS(flash)
    num_blocks = 80
    populate_initial_data(fs, num_blocks)
    workload = generate_workload("uniform", num_blocks, 250, seed=seed)
    for op, lba in enumerate(workload):
        fs.write(lba, f"v_{op}")

    assert len(fs.l2p) == num_blocks
    assert flash.total_valid_pages == num_blocks
    for lba, ppa in fs.l2p.items():
        st, _, mapped_lba = flash.read_page(ppa)
        assert st == PageState.VALID and mapped_lba == lba
    print("[PASS] Validation 1: Each logical block maps to exactly one valid physical page.")

    # 2. GC Data Preservation validation
    flash2 = FlashDevice(num_segments=8, pages_per_segment=16)
    metrics2 = MetricsTracker()
    fs2 = LogStructuredFS(flash2, metrics2)
    expected_data = {}
    for lba in range(90):
        fs2.write(lba, f"initial_{lba}")
        expected_data[lba] = f"initial_{lba}"
    metrics2.start_measuring()

    workload2 = generate_workload("skewed", 90, 500, seed=seed)
    for op, lba in enumerate(workload2):
        val = f"updated_op{op}_lba{lba}"
        fs2.write(lba, val)
        expected_data[lba] = val
    metrics2.stop_measuring()

    assert metrics2.gc_runs > 0, "GC should have executed during heavy updates."
    for lba in range(90):
        assert fs2.read(lba) == expected_data[lba], f"Data corruption detected at LBA {lba}!"
    print(f"[PASS] Validation 2: Garbage collection preserves data integrity ({metrics2.gc_runs} GC cycles verified).")

    # 3. Direct Overwrite Prevention validation
    flash3 = FlashDevice(num_segments=4, pages_per_segment=8)
    flash3.write_page(0, "first", lba=0)
    try:
        flash3.write_page(0, "overwrite_attempt", lba=0)
        assert False, "Should have raised RuntimeError on overwriting non-free page."
    except RuntimeError:
        pass
    print("[PASS] Validation 3: Flash device strictly prevents overwrites to non-free pages.")

    # 4. Reproducibility validation
    exp_a = experiments.run_strategy_comparison(num_segments=8, pages_per_segment=16, num_updates=200, seed=seed)
    exp_b = experiments.run_strategy_comparison(num_segments=8, pages_per_segment=16, num_updates=200, seed=seed)
    assert exp_a == exp_b, "Runs with identical random seeds must produce identical results."
    print("[PASS] Validation 4: Simulator produces 100% deterministic, reproducible results.")

    print("\nAll validation checks passed successfully!\n")
    return True


def format_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Formats data rows into a clean CLI ASCII table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(cell)))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_str = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"

    lines = [sep, header_str, sep]
    for row in rows:
        row_str = "| " + " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)) + " |"
        lines.append(row_str)
    lines.append(sep)
    return "\n".join(lines)


def run_all(seed: int = 42, num_updates: int = 2000, results_dir: str = "results") -> None:
    os.makedirs(results_dir, exist_ok=True)

    # 1. Validation
    validate_simulator(seed=seed)

    # 2. Experiment 1: In-Place vs Log-Structured
    print_banner("Experiment 1: Strategy Comparison (In-Place vs. Log-Structured)")
    print(f"Parameters: 32 segments, 64 pages/seg (2048 pages total), 70% utilization (1433 blocks), {num_updates} updates (seed={seed})")

    res1 = experiments.run_strategy_comparison(
        num_segments=32,
        pages_per_segment=64,
        utilization=0.70,
        num_updates=num_updates,
        seed=seed,
    )

    headers1 = ["Strategy", "Logical Writes", "Physical Writes", "WAF", "Segment Erases", "GC Invocations", "GC Pages Copied"]
    rows1 = [
        [
            "In-Place Baseline",
            res1["in_place"]["logical_writes"],
            res1["in_place"]["physical_writes"],
            f"{res1['in_place']['waf']:.4f}",
            res1["in_place"]["segment_erases"],
            res1["in_place"]["gc_runs"],
            res1["in_place"]["gc_pages_copied"],
        ],
        [
            "Log-Structured (F2FS)",
            res1["log_structured"]["logical_writes"],
            res1["log_structured"]["physical_writes"],
            f"{res1['log_structured']['waf']:.4f}",
            res1["log_structured"]["segment_erases"],
            res1["log_structured"]["gc_runs"],
            res1["log_structured"]["gc_pages_copied"],
        ],
    ]
    print(format_table(headers1, rows1))

    csv_path1 = os.path.join(results_dir, "experiment_1_strategy_comparison.csv")
    png_path1 = os.path.join(results_dir, "waf_strategy_comparison.png")
    experiments.save_experiment_1_csv(res1, csv_path1)
    visualization.plot_strategy_comparison(res1, png_path1)
    print(f"Saved: {csv_path1}")
    print(f"Saved: {png_path1}")

    # 3. Experiment 2: Storage Utilization
    print_banner("Experiment 2: Log-Structured Performance vs. Storage Utilization")
    print(f"Parameters: 32 segments, 64 pages/seg (2048 pages total), {num_updates} updates, Utilizations: 40%, 60%, 80%, 95%")

    res2 = experiments.run_utilization_experiment(
        num_segments=32,
        pages_per_segment=64,
        utilizations=(0.40, 0.60, 0.80, 0.95),
        num_updates=num_updates,
        seed=seed,
    )

    headers2 = ["Utilization", "Active Blocks", "Logical Writes", "Physical Writes", "WAF", "Segment Erases", "GC Runs", "GC Copied"]
    rows2 = [
        [
            r["utilization_pct"],
            r["num_blocks"],
            r["logical_writes"],
            r["physical_writes"],
            f"{r['waf']:.4f}",
            r["segment_erases"],
            r["gc_runs"],
            r["gc_pages_copied"],
        ]
        for r in res2
    ]
    print(format_table(headers2, rows2))

    csv_path2 = os.path.join(results_dir, "experiment_2_utilization.csv")
    png_path2 = os.path.join(results_dir, "waf_vs_utilization.png")
    experiments.save_experiment_2_csv(res2, csv_path2)
    visualization.plot_utilization_curve(res2, png_path2)
    print(f"Saved: {csv_path2}")
    print(f"Saved: {png_path2}")

    # 4. Experiment 3: Workload Skew
    print_banner("Experiment 3: Workload Skew Comparison (Uniform vs. Skewed 80/20)")
    print(f"Parameters: 32 segments, 64 pages/seg, 80% utilization (1638 blocks), {num_updates} updates")

    res3 = experiments.run_workload_comparison(
        num_segments=32,
        pages_per_segment=64,
        utilization=0.80,
        num_updates=num_updates,
        seed=seed,
    )

    headers3 = ["Workload Type", "Logical Writes", "Physical Writes", "WAF", "Segment Erases", "GC Runs", "GC Copied"]
    rows3 = [
        [
            "Uniform (Equal Probability)",
            res3["uniform"]["logical_writes"],
            res3["uniform"]["physical_writes"],
            f"{res3['uniform']['waf']:.4f}",
            res3["uniform"]["segment_erases"],
            res3["uniform"]["gc_runs"],
            res3["uniform"]["gc_pages_copied"],
        ],
        [
            "Skewed (80/20 Pareto Rule)",
            res3["skewed"]["logical_writes"],
            res3["skewed"]["physical_writes"],
            f"{res3['skewed']['waf']:.4f}",
            res3["skewed"]["segment_erases"],
            res3["skewed"]["gc_runs"],
            res3["skewed"]["gc_pages_copied"],
        ],
    ]
    print(format_table(headers3, rows3))

    csv_path3 = os.path.join(results_dir, "experiment_3_workload_skew.csv")
    png_path3 = os.path.join(results_dir, "waf_workload_comparison.png")
    experiments.save_experiment_3_csv(res3, csv_path3)
    visualization.plot_workload_comparison(res3, png_path3)
    print(f"Saved: {csv_path3}")
    print(f"Saved: {png_path3}")

    print_banner("Simulation Complete")
    print("All experiments completed successfully.")
    print(f"Generated results and figures in '{results_dir}/':")
    for f in sorted(os.listdir(results_dir)):
        print(f" - {f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="F2FS-Inspired Flash Storage Simulator (In-Place vs. Log-Structured)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible workloads (default: 42)")
    parser.add_argument("--updates", type=int, default=2000, help="Number of write update operations per run (default: 2000)")
    parser.add_argument("--results-dir", type=str, default="results", help="Directory to save CSVs and PNGs (default: results)")

    args = parser.parse_args()
    run_all(seed=args.seed, num_updates=args.updates, results_dir=args.results_dir)


if __name__ == "__main__":
    main()
