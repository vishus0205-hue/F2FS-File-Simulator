"""
Visualization Module for Flash Storage Simulator.

Generates the three required Matplotlib graphs:
1. WAF comparison between In-Place and Log-Structured strategies.
2. WAF vs. Storage Utilization (40%, 60%, 80%, 95%).
3. WAF comparison between Uniform and Skewed workloads.

Saves figures as high-resolution PNG files.
"""

import os
from typing import Any, Dict, List
import matplotlib.pyplot as plt


def set_plot_style() -> None:
    """Sets a clean, modern aesthetic style for Matplotlib."""
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.size"] = 11
    plt.rcParams["axes.edgecolor"] = "#cccccc"
    plt.rcParams["axes.linewidth"] = 1.0


def plot_strategy_comparison(results: Dict[str, Dict[str, Any]], output_path: str) -> None:
    """
    Graph 1: WAF comparison between In-Place and Log-Structured strategies.
    """
    set_plot_style()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    strategies = ["In-Place Baseline", "Log-Structured (F2FS)"]
    waf_values = [results["in_place"]["waf"], results["log_structured"]["waf"]]
    colors = ["#e63946", "#2a9d8f"]

    fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
    bars = ax.bar(strategies, waf_values, color=colors, width=0.45, edgecolor="#333333", linewidth=1.2)

    ax.set_ylabel("Write Amplification Factor (WAF)", fontsize=12, fontweight="bold")
    ax.set_title("Experiment 1: Write Amplification Factor by Strategy", fontsize=13, fontweight="bold", pad=15)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    ax.set_axisbelow(True)

    # Annotate value on top of each bar
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            f"{height:.2f}x",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontweight="bold",
            fontsize=11,
        )

    # Add headroom for annotation
    ax.set_ylim(0, max(waf_values) * 1.15)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def plot_utilization_curve(results: List[Dict[str, Any]], output_path: str) -> None:
    """
    Graph 2: WAF versus storage utilization (40%, 60%, 80%, 95%).
    """
    set_plot_style()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    labels = [r["utilization_pct"] for r in results]
    waf_values = [r["waf"] for r in results]

    fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
    line = ax.plot(
        labels,
        waf_values,
        marker="o",
        color="#1d3557",
        linewidth=2.5,
        markersize=8,
        markerfacecolor="#e76f51",
        markeredgecolor="#1d3557",
        markeredgewidth=1.5,
    )

    ax.set_xlabel("Initial Storage Utilization", fontsize=12, fontweight="bold")
    ax.set_ylabel("Write Amplification Factor (WAF)", fontsize=12, fontweight="bold")
    ax.set_title("Experiment 2: Log-Structured WAF vs. Storage Utilization", fontsize=13, fontweight="bold", pad=15)
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.set_axisbelow(True)

    # Annotate points
    for x, y in zip(labels, waf_values):
        ax.annotate(
            f"{y:.2f}x",
            xy=(x, y),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontweight="bold",
            fontsize=11,
        )

    ax.set_ylim(min(0.8, min(waf_values) * 0.9), max(waf_values) * 1.25)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def plot_workload_comparison(results: Dict[str, Dict[str, Any]], output_path: str) -> None:
    """
    Graph 3: WAF comparison between Uniform and Skewed workloads.
    """
    set_plot_style()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    workloads = ["Uniform (Equal)", "Skewed (80/20 Rule)"]
    waf_values = [results["uniform"]["waf"], results["skewed"]["waf"]]
    colors = ["#457b9d", "#f4a261"]

    fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
    bars = ax.bar(workloads, waf_values, color=colors, width=0.45, edgecolor="#333333", linewidth=1.2)

    ax.set_ylabel("Write Amplification Factor (WAF)", fontsize=12, fontweight="bold")
    ax.set_title("Experiment 3: Log-Structured WAF by Workload Distribution", fontsize=13, fontweight="bold", pad=15)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    ax.set_axisbelow(True)

    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            f"{height:.2f}x",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontweight="bold",
            fontsize=11,
        )

    ax.set_ylim(0, max(waf_values) * 1.25)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
