# ⚡ F2FS-Inspired Flash Storage Simulator
### *In-Place Updates vs. Log-Structured Writes on NAND Flash Memory*

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](#-how-to-run-this-project)
[![Pytest](https://img.shields.io/badge/Pytest-25%2F25%20PASSED-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](#-running-the-test-suite)
[![WAF Reduction](https://img.shields.io/badge/WAF%20Reduction-36.4%C3%97%20Gain-FF5722?style=for-the-badge&logo=speedtest&logoColor=white)](#-empirical-benchmarks)
[![Hardware Enforced](https://img.shields.io/badge/Hardware-Erase--Before--Write-4CAF50?style=for-the-badge&logo=microchip&logoColor=white)](#-3d-flash-hardware-anatomy)
[![Interactive GUI](https://img.shields.io/badge/Live%20Studio-Web%20GUI%20Included-7952B3?style=for-the-badge&logo=googlechrome&logoColor=white)](#-mode-2-interactive-web-gui-live-studio)

<br/>

> **A dual-engine (Python CLI & Interactive Web GUI) architectural simulator demonstrating how Flash-Friendly File Systems (F2FS) overcome NAND flash physical wear, slashing Write Amplification from 63.34× down to 1.74×.**

</div>

---

## 📑 Table of Contents
1. [3D Flash Hardware Anatomy](#-3d-flash-hardware-anatomy)
2. [Architectural Overview](#-architectural-overview)
3. [How to Run This Project](#-how-to-run-this-project)
   - [Prerequisites & Environment Setup](#1-prerequisites--environment-setup)
   - [Mode 1: Automated Benchmark & Experiment Suite (CLI)](#2-mode-1-automated-benchmark--experiment-suite-cli)
   - [Mode 2: Interactive Web GUI Live Studio](#3-mode-2-interactive-web-gui-live-studio)
   - [Mode 3: Comprehensive Verification & Pytest Suite](#4-mode-3-comprehensive-verification--pytest-suite)
4. [In-Place Updates vs. Log-Structured Writes](#-in-place-updates-vs-log-structured-writes)
5. [Empirical Benchmarks & Visual Analytics](#-empirical-benchmarks--visual-analytics)
   - [Experiment 1: Strategy Comparison (In-Place vs. F2FS)](#experiment-1-strategy-comparison)
   - [Experiment 2: Storage Utilization Curve](#experiment-2-storage-utilization-curve)
   - [Experiment 3: Workload Skew (Uniform vs. 80/20 Pareto)](#experiment-3-workload-skew)
6. [Formal Mathematics & Metrics](#-formal-mathematics--metrics)
7. [Validation Invariants (Specification Section 1.H)](#-validation-invariants-specification-section-1h)
8. [Codebase Organization](#-codebase-organization)

---

## 🧊 3D Flash Hardware Anatomy

NAND flash memory departs fundamentally from magnetic spinning disks. It enforces an unforgiving **erase-before-write** physics constraint:

```
                  ┌──────────────────────────────────────────────┐
                 ╱                                              ╱│
                ╱           NAND FLASH MEMORY ARRAY            ╱ │
               ┌──────────────────────────────────────────────┐  │
               │  Segment 0     Segment 1     Segment K       │  │
               │ ┌──────────┐  ┌──────────┐  ┌──────────┐     │  │
               │ │ Page 0   │  │ Page 0   │  │ Page 0   │ ... │  │
               │ │ Page 1   │  │ Page 1   │  │ Page 1   │     │  │
  ERASE UNIT   │ │ ...      │  │ ...      │  │ ...      │     │  │
 (Segment-level│ │ Page 63  │  │ Page 63  │  │ Page 63  │     │  │
   e.g. 256KB) │ └──────────┘  └──────────┘  └──────────┘     │  │
               │  [Erase: Seg]  [Erase: Seg]  [Erase: Seg]    │ ╱
               └──────────────────────────────────────────────┘╱
               │  ▲  ▲  ▲  ▲    ▲  ▲  ▲  ▲    ▲  ▲  ▲  ▲      │
               └──┼──┼──┼──┼────┼──┼──┼──┼────┼──┼──┼──┼──────┘
                  │  │  │  │    │  │  │  │    │  │  │  │
               WRITE / READ UNIT: Page-level (4 KB Granularity)
```

### 3D Page Lifecycle & State Transitions

A physical flash page can only transition through a strictly bounded, non-reversible forward loop:

```
                        ┌─────────────┐
        ┌──────────────▶│    FREE     │◀──────────────┐
        │               │ (Clean 0xFF)│               │
        │               └──────┬──────┘               │
        │                      │                      │
        │                 Write Page                  │
        │               (Out-of-Place)                │
        │                      ▼                      │
   Segment Erase        ┌─────────────┐          Segment Erase
  (Resets entire        │    VALID    │         (Resets entire
     segment)           │ (Live Data) │            segment)
        │               └──────┬──────┘               │
        │                      │                      │
        │                 LBA Updated                 │
        │                (Superseded)                 │
        │                      ▼                      │
        │               ┌─────────────┐               │
        └───────────────┤   INVALID   ├───────────────┘
                        │ (Dead Data) │
                        └─────────────┘
```

> **Hardware Overwrite Enforcement**: Any direct write attempt directed to an already occupied (`VALID` or `INVALID`) physical page without an intervening erase immediately triggers a hardware-level `RuntimeError`.

---

## 🏛️ Architectural Overview

The simulator architecture separates physical flash primitives from high-level filesystem policies:

```mermaid
graph TD
    subgraph L3["Layer 3: Workload & Application Engine"]
        W1[Uniform Random Generator]
        W2[Pareto 80/20 Skew Generator]
        CLI[main.py CLI Orchestrator]
        WEB[Interactive Web Studio app.js]
    end

    subgraph L2["Layer 2: Filesystem Abstraction & Translation"]
        direction TB
        IP[InPlaceFS: Static 1-to-1 PPA=LBA]
        LS[LogStructuredFS: F2FS-Inspired Append Log]
        MAP[L2P & P2L In-Memory Mapping Tables]
        GC[Greedy Garbage Collector: Minimum-Cost Victim Selection]
        MET[Metrics Tracker: WAF, Writes, Segment Erases]
    end

    subgraph L1["Layer 1: Physical Flash Device Hardware"]
        DEV[FlashDevice Hardware Simulator]
        SEG[Segment Array: 32 Segments × 64 Pages]
        PROT[Zero-Overwrite Hardware Invariant Trap]
    end

    L3 --> L2
    LS <--> MAP
    LS --> GC
    IP --> DEV
    LS --> DEV
    DEV --> SEG
    DEV --> PROT
    L2 --> MET
```

---

## 🚀 How to Run This Project

### 1. Prerequisites & Environment Setup

* **Python**: Version `3.8` or newer (tested on Python 3.8, 3.10, 3.11, 3.12, 3.13)
* **Web Browser**: Any modern browser (Chrome, Edge, Firefox, Safari) for the Interactive Web Studio

Clone the repository and install the minimal required packages:

```bash
# 1. Clone repository (or navigate to project root)
cd "F2FS File Simulator"

# 2. (Recommended) Create and activate virtual environment
python -m venv venv

# Windows (Command Prompt / PowerShell):
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# 3. Install core dependencies
pip install -r requirements.txt
```

*Contents of `requirements.txt`: `numpy`, `matplotlib`, `pytest`.*

---

### 2. Mode 1: Automated Benchmark & Experiment Suite (CLI)

Run the full end-to-end simulation pipeline with a single command:

```bash
python main.py
```

#### What happens during execution:
1. **Self-Validation Suite**: Automatically executes and verifies all 4 system invariants (1-to-1 mapping, GC data integrity, overwrite protection, and deterministic reproducibility).
2. **Experiment 1 (Strategy Comparison)**: Benchmarks `InPlaceFS` against `LogStructuredFS` over 2,000 updates at 70% utilization.
3. **Experiment 2 (Storage Utilization)**: Evaluates F2FS across 40%, 60%, 80%, and 95% utilization.
4. **Experiment 3 (Workload Skew)**: Compares Uniform vs. Skewed (80/20 Pareto) access patterns.
5. **Output Generation**:
   * Renders high-resolution ASCII comparison tables directly in your terminal.
   * Exports raw CSV records to `results/`.
   * Generates publication-ready Matplotlib PNG charts in `results/`.

#### CLI Customization Options:
You can customize seeds, write update counts, or redirect output directories:

```bash
# Run with custom seed and 5,000 write updates
python main.py --seed 123 --updates 5000

# Specify a custom results output directory
python main.py --results-dir my_custom_results

# Display complete CLI argument documentation
python main.py --help
```

---

### 3. Mode 2: Interactive Web GUI Live Studio

This repository includes a standalone, browser-based **Live Flash Studio** with animated page allocation, live block visualizer, and Chart.js telemetry.

```bash
# Option A: Built-in Python HTTP Server (Recommended)
python -m http.server 8000
```
Then open your web browser at:
👉 **`http://localhost:8000/index.html`**

*(Option B: You can also directly double-click or drag-and-drop `index.html` into any browser.)*

#### Interactive Studio Features:
* 🎛️ **Strategy Toggle**: Switch instantly between **Log-Structured (F2FS)** and **In-Place Baseline** to observe live behavioral divergence.
* ✍️ **Write LBA**: Dispatch individual random logical block updates.
* 🔥 **Hot Write (80/20)**: Inject skewed workload bursts into hot cache lines.
* ⚡ **Batch 20 Writes**: Rapidly step through allocation cycles and watch segments fill.
* ♻️ **Run GC**: Manually trigger Greedy Garbage Collection to inspect victim segment selection, page migration, and segment erasure in real-time.
* 🔍 **Interactive Segment Grid**: Hover over any physical block to inspect segment index, page state (`FREE`, `VALID`, `INVALID`), and wear erase count.

---

### 4. Mode 3: Comprehensive Verification & Pytest Suite

Run all 25 unit and invariant verification tests:

```bash
# Run complete test suite with verbose reporting
pytest -v
```

#### Run Specific Test Modules:
```bash
# Run Section 1.H formal specification validation checks
pytest tests/test_validation.py -v

# Run hardware flash constraints & overwrite prevention tests
pytest tests/test_flash.py -v

# Run filesystem out-of-place and in-place semantics
pytest tests/test_filesystem.py -v

# Run garbage collection victim selection and page migration tests
pytest tests/test_gc.py -v

# Run extended stress & boundary correctness tests
pytest tests/test_correctness.py -v
```

---

## ⚖️ In-Place Updates vs. Log-Structured Writes

| Dimension | In-Place Baseline (`InPlaceFS`) | Log-Structured (`LogStructuredFS`) |
| :--- | :--- | :--- |
| **Physical Address Mapping** | Static (`PPA = LBA`) | Virtualized via dynamic `L2P` & `P2L` tables |
| **Update Mechanism** | Overwrites at original physical location | Appends sequentially to active clean segment |
| **Handling Stale Data** | Read entire segment $\to$ Erase segment $\to$ Rewrite segment | Marks old physical page as `INVALID` out-of-place |
| **Erase Frequency** | **1 Erase cycle on EVERY single update** | **Batch-reclaimed** only when free segments deplete |
| **Garbage Collection** | None (Synchronous inline rewrite penalty) | **Greedy GC**: Migrates valid pages, erases victims |
| **Write Amplification (WAF)**| **Extreme (~63.34×)** | **Low (~1.74×)** |
| **Flash Endurance Impact** | Destructive; burns out flash cells rapidly | High longevity; smooth sequential wear |

---

## 📊 Empirical Benchmarks & Visual Analytics

### Experiment 1: Strategy Comparison
*Configuration: 32 Segments × 64 Pages (2,048 pages total), 70% utilization (1,433 active blocks), 2,000 updates, uniform distribution.*

| Strategy | Logical Writes | Physical Writes | WAF | Segment Erases | GC Runs | GC Copied Pages |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **In-Place Baseline** | 2,000 | 126,674 | **63.34×** | 2,000 | 0 | 0 |
| **Log-Structured (F2FS)** | 2,000 | 3,478 | **1.74×** | 46 | 46 | 1,478 |

![WAF Strategy Comparison](results/waf_strategy_comparison.png)

> **Key Insight**: F2FS reduces physical write amplification by **36.4×** and cuts destructive erase cycles from **2,000 down to 46**, extending NAND flash lifespan by over 4,300%.

---

### Experiment 2: Storage Utilization Curve
*Configuration: Log-Structured FS, 2,000 updates, varying storage capacity fill.*

| Storage Utilization | Active Blocks | Logical Writes | Physical Writes | WAF | Segment Erases | GC Copied Pages |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **40%** | 819 | 2,000 | 2,111 | **1.06×** | 15 | 111 |
| **60%** | 1,228 | 2,000 | 2,718 | **1.36×** | 31 | 718 |
| **80%** | 1,638 | 2,000 | 5,326 | **2.66×** | 78 | 3,326 |
| **95%** | 1,945 | 2,000 | 37,478 | **18.74×** | 585 | 35,478 |

![WAF vs Utilization](results/waf_vs_utilization.png)

> **Key Insight**: As storage utilization exceeds 80% and enters near-full capacity (95%), free segments become scarce. Victim segments contain predominantly valid pages that must be migrated before erasing, triggering an exponential surge in WAF.

---

### Experiment 3: Workload Skew
*Configuration: Log-Structured FS, 80% utilization (1,638 blocks), 2,000 updates.*

| Access Pattern | Logical Writes | Physical Writes | WAF | Segment Erases | GC Runs | GC Copied Pages |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Uniform (Equal Probability)** | 2,000 | 5,326 | **2.66×** | 78 | 78 | 3,326 |
| **Skewed (80/20 Pareto Rule)** | 2,000 | 4,878 | **2.44×** | 71 | 71 | 2,878 |

![WAF Workload Comparison](results/waf_workload_comparison.png)

> **Key Insight**: Skewed workloads concentrate updates on a compact subset of "hot" blocks, clustering stale (`INVALID`) pages into fewer segments. The greedy garbage collector reclaims these high-invalid segments with far fewer page migrations.

---

## 📐 Formal Mathematics & Metrics

### 1. Write Amplification Factor (WAF)
$$\text{WAF} = \frac{\text{Total Physical Page Writes}}{\text{Total Logical Page Writes}} = \frac{W_{\text{user}} + W_{\text{GC}}}{W_{\text{user}}}$$

Where:
* $W_{\text{user}}$: Direct logical write requests issued by the workload.
* $W_{\text{GC}}$: Additional physical writes incurred during garbage collection migration.
* *Note: Setup / preconditioning data population is strictly excluded from measurement windows.*

### 2. Greedy Victim Selection Cost Model
$$\text{Victim Segment} = \arg\min_{s \in \mathcal{S}_{\text{closed}}} V(s)$$

Where $V(s)$ represents the count of surviving `VALID` pages in segment $s$. Minimizing $V(s)$ maximizes reclaimed free pages $P - V(s)$ per erase cycle.

---

## 🛡️ Validation Invariants (Specification Section 1.H)

All four formal invariants defined in the simulator specification are strictly tested and verified:

* [x] **Invariant 1: Exact 1-to-1 Mapping**  
  Every active logical block address ($\text{LBA} \in [0, N-1]$) maps to precisely one `VALID` physical page address ($\text{PPA}$) across all tables (`L2P` and `P2L`).
* [x] **Invariant 2: Lossless GC Data Preservation**  
  Under heavy update workloads and dozens of consecutive GC cycles, reading back any LBA yields the exact latest data payload with zero data loss or byte corruption.
* [x] **Invariant 3: Physical Overwrite Prevention**  
  The underlying flash memory controller physically prevents overwrites: calling `write_page` on any non-`FREE` page raises an unhandled `RuntimeError`.
* [x] **Invariant 4: Deterministic Reproducibility**  
  Fixed random seeds guarantee identical pseudo-random workload schedules, metrics, and figures across independent runs.

---

## 📂 Codebase Organization

```
f2fs-simulator/
├── main.py                  # CLI simulation runner & experiment orchestrator
├── flash.py                 # Flash memory hardware simulator (pages, states, erases)
├── filesystem.py            # InPlaceFS & LogStructuredFS implementations
├── garbage_collector.py     # Greedy Garbage Collection & page migration engine
├── workloads.py             # Uniform & Skewed (80/20 Pareto) workload generators
├── metrics.py               # WAF, write counters, and erase tracker
├── experiments.py           # Experiment 1, 2, and 3 implementation logic
├── visualization.py         # Matplotlib publication chart generators
├── requirements.txt         # Project dependencies (numpy, matplotlib, pytest)
├── index.html               # Interactive Web Studio (HTML5 GUI)
├── style.css                # Modern design styling for Web Studio
├── app.js                   # Client-side simulator engine & live telemetry
├── README.md                # 3D project documentation & run instructions
├── tests/                   # 25-test verification suite
│   ├── test_flash.py        # Flash hardware invariants & overwrite traps
│   ├── test_filesystem.py   # In-place vs log-structured write semantics
│   ├── test_gc.py           # Greedy victim selection & migration tests
│   ├── test_validation.py   # Section 1.H four invariant verification tests
│   └── test_correctness.py  # Boundary conditions & reserve capacity tests
└── results/                 # Exported benchmark CSV datasets & PNG graphs
    ├── experiment_1_strategy_comparison.csv
    ├── experiment_2_utilization.csv
    ├── experiment_3_workload_skew.csv
    ├── waf_strategy_comparison.png
    ├── waf_vs_utilization.png
    └── waf_workload_comparison.png
```

---

## 📚 References & Literature

1. **Lee, C., Sim, D., Hwang, J., & Cho, S.** (2015). *F2FS: A New File System for Flash Storage*. In 13th USENIX Conference on File and Storage Technologies (FAST '15), pp. 273-286.
2. **Rosenblum, M., & Ousterhout, J. K.** (1992). *The Design and Implementation of a Log-Structured File System*. ACM Transactions on Computer Systems (TOCS), 10(1), 26-52.
3. **Agrawal, N., Prabhakaran, V., Wobber, T., Davis, J. D., Manasse, M., & Panigrahy, R.** (2008). *Design Tradeoffs for SSD Performance*. In USENIX Annual Technical Conference (ATC '08).
