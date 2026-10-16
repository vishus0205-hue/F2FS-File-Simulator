"""
Experiments Module for Flash Storage Simulator.

Executes the three specified experiments:
1. Strategy Comparison: In-Place Baseline vs. Log-Structured FS under identical workload.
2. Utilization Impact: Log-Structured FS performance at 40%, 60%, 80%, and 95% initial utilization.
3. Workload Comparison: Uniform vs. Skewed (80/20) update distributions on Log-Structured FS.
"""

import csv
import os
from typing import Any, Dict, List, Tuple
from flash import FlashDevice
from filesystem import InPlaceFS, LogStructuredFS
from metrics import MetricsTracker
from workloads import generate_workload, populate_initial_data


def run_strategy_comparison(
    num_segments: int = 32,
    pages_per_segment: int = 64,
    utilization: float = 0.70,
    num_updates: int = 2000,
    seed: int = 42,
) -> Dict[str, Dict[str, Any]]:
    """
    Experiment 1: Compare in-place updates vs. log-structured writes.
    Both systems are initialized to the same capacity utilization and
    subjected to the exact same update sequence.
    """
    total_pages = num_segments * pages_per_segment
    num_blocks = int(total_pages * utilization)

    # 1. In-Place Strategy
    flash_inplace = FlashDevice(num_segments, pages_per_segment)
    metrics_inplace = MetricsTracker()
    fs_inplace = InPlaceFS(flash_inplace, metrics_inplace)
    populate_initial_data(fs_inplace, num_blocks)

    workload = generate_workload("uniform", num_blocks, num_updates, seed=seed)

    metrics_inplace.start_measuring()
    for op_idx, lba in enumerate(workload):
        fs_inplace.write(lba, f"update_{op_idx}")
    metrics_inplace.stop_measuring()

    # 2. Log-Structured Strategy
    flash_log = FlashDevice(num_segments, pages_per_segment)
    metrics_log = MetricsTracker()
    fs_log = LogStructuredFS(flash_log, metrics_log)
    populate_initial_data(fs_log, num_blocks)

    metrics_log.start_measuring()
    for op_idx, lba in enumerate(workload):
        fs_log.write(lba, f"update_{op_idx}")
    metrics_log.stop_measuring()

    return {
        "in_place": metrics_inplace.to_dict(),
        "log_structured": metrics_log.to_dict(),
    }


def run_utilization_experiment(
    num_segments: int = 32,
    pages_per_segment: int = 64,
    utilizations: Tuple[float, ...] = (0.40, 0.60, 0.80, 0.95),
    num_updates: int = 2000,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    Experiment 2: Compare log-structured performance across initial utilizations:
    40%, 60%, 80%, and 95%.
    """
    total_pages = num_segments * pages_per_segment
    results: List[Dict[str, Any]] = []

    for util in utilizations:
        num_blocks = int(total_pages * util)
        flash = FlashDevice(num_segments, pages_per_segment)
        metrics = MetricsTracker()
        fs = LogStructuredFS(flash, metrics)

        populate_initial_data(fs, num_blocks)
        workload = generate_workload("uniform", num_blocks, num_updates, seed=seed)

        metrics.start_measuring()
        for op_idx, lba in enumerate(workload):
            fs.write(lba, f"update_{op_idx}")
        metrics.stop_measuring()

        data = metrics.to_dict()
        data["utilization"] = util
        data["utilization_pct"] = f"{int(round(util * 100))}%"
        data["num_blocks"] = num_blocks
        results.append(data)

    return results


def run_workload_comparison(
    num_segments: int = 32,
    pages_per_segment: int = 64,
    utilization: float = 0.80,
    num_updates: int = 2000,
    seed: int = 42,
) -> Dict[str, Dict[str, Any]]:
    """
    Experiment 3: Compare Uniform vs. Skewed (80/20) workloads on Log-Structured FS.
    """
    total_pages = num_segments * pages_per_segment
    num_blocks = int(total_pages * utilization)

    results: Dict[str, Dict[str, Any]] = {}

    for w_type in ("uniform", "skewed"):
        flash = FlashDevice(num_segments, pages_per_segment)
        metrics = MetricsTracker()
        fs = LogStructuredFS(flash, metrics)

        populate_initial_data(fs, num_blocks)
        workload = generate_workload(w_type, num_blocks, num_updates, seed=seed)

        metrics.start_measuring()
        for op_idx, lba in enumerate(workload):
            fs.write(lba, f"update_{op_idx}")
        metrics.stop_measuring()

        data = metrics.to_dict()
        data["workload"] = w_type
        results[w_type] = data

    return results


def save_experiment_1_csv(results: Dict[str, Dict[str, Any]], filepath: str) -> None:
    """Saves Experiment 1 results to CSV."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fieldnames = [
        "strategy",
        "logical_writes",
        "physical_writes",
        "waf",
        "segment_erases",
        "gc_runs",
        "gc_pages_copied",
    ]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for strategy, metrics in results.items():
            row = {"strategy": strategy, **metrics}
            writer.writerow(row)


def save_experiment_2_csv(results: List[Dict[str, Any]], filepath: str) -> None:
    """Saves Experiment 2 results to CSV."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fieldnames = [
        "utilization_pct",
        "utilization",
        "num_blocks",
        "logical_writes",
        "physical_writes",
        "waf",
        "segment_erases",
        "gc_runs",
        "gc_pages_copied",
    ]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)


def save_experiment_3_csv(results: Dict[str, Dict[str, Any]], filepath: str) -> None:
    """Saves Experiment 3 results to CSV."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fieldnames = [
        "workload",
        "logical_writes",
        "physical_writes",
        "waf",
        "segment_erases",
        "gc_runs",
        "gc_pages_copied",
    ]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for workload, metrics in results.items():
            row = {"workload": workload, **metrics}
            writer.writerow(row)
