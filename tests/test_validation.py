"""
Validation tests according to specification section 1.H:
1. Ensure each logical block maps to exactly one valid physical page.
2. Ensure garbage collection preserves data.
3. Verify that no write targets a non-free page.
4. Verify reproducibility using the same random seed.
"""

import pytest
from flash import FlashDevice, PageState
from filesystem import LogStructuredFS, InPlaceFS
from metrics import MetricsTracker
from workloads import generate_workload, populate_initial_data
from experiments import run_strategy_comparison


def test_validation_1_each_lba_maps_to_exactly_one_valid_ppa():
    """Ensure each logical block maps to exactly one valid physical page."""
    flash = FlashDevice(num_segments=8, pages_per_segment=16)
    fs = LogStructuredFS(flash)
    num_blocks = 80

    populate_initial_data(fs, num_blocks)
    workload = generate_workload("uniform", num_blocks, 300, seed=123)

    for op, lba in enumerate(workload):
        fs.write(lba, f"data_{op}")

    # Check 1: Every mapped LBA points to a VALID page with matching LBA
    for lba, ppa in fs.l2p.items():
        state, _, page_lba = flash.read_page(ppa)
        assert state == PageState.VALID
        assert page_lba == lba

    # Check 2: Total valid physical pages on device equals the number of logical blocks
    assert flash.total_valid_pages == num_blocks
    assert len(fs.l2p) == num_blocks

    # Check 3: No two LBAs map to the same PPA
    mapped_ppas = list(fs.l2p.values())
    assert len(mapped_ppas) == len(set(mapped_ppas))


def test_validation_2_gc_preserves_data():
    """Ensure garbage collection preserves data across heavy updates and multiple GC runs."""
    flash = FlashDevice(num_segments=8, pages_per_segment=16)
    metrics = MetricsTracker()
    fs = LogStructuredFS(flash, metrics)
    num_blocks = 90  # ~70% utilization of 128 pages

    populate_initial_data(fs, num_blocks)
    metrics.start_measuring()

    expected_data = {lba: f"block_{lba}_init" for lba in range(num_blocks)}

    # Heavy updates to trigger multiple GC cycles
    workload = generate_workload("skewed", num_blocks, 600, seed=42)
    for op, lba in enumerate(workload):
        new_val = f"updated_val_{op}_{lba}"
        fs.write(lba, new_val)
        expected_data[lba] = new_val

    metrics.stop_measuring()

    # Verify that GC actually ran
    assert metrics.gc_runs > 0
    assert metrics.gc_pages_copied > 0

    # Verify every single logical block returns its exact expected data
    for lba in range(num_blocks):
        actual_val = fs.read(lba)
        assert actual_val == expected_data[lba], f"Data mismatch at LBA {lba}"


def test_validation_3_no_write_targets_non_free_page():
    """Verify that no write targets a non-free page directly on the flash device."""
    flash = FlashDevice(num_segments=6, pages_per_segment=16)
    fs = LogStructuredFS(flash)
    num_blocks = 70

    populate_initial_data(fs, num_blocks)
    workload = generate_workload("uniform", num_blocks, 400, seed=999)

    # If any write targets a non-free page, FlashDevice.write_page raises RuntimeError
    try:
        for op, lba in enumerate(workload):
            fs.write(lba, f"payload_{op}")
    except RuntimeError as e:
        pytest.fail(f"Write violation occurred: {e}")


def test_validation_4_reproducibility_with_same_seed():
    """Verify reproducibility using the same random seed."""
    run_a = run_strategy_comparison(
        num_segments=8,
        pages_per_segment=16,
        utilization=0.75,
        num_updates=400,
        seed=101,
    )
    run_b = run_strategy_comparison(
        num_segments=8,
        pages_per_segment=16,
        utilization=0.75,
        num_updates=400,
        seed=101,
    )

    # Both runs should yield identical metrics
    assert run_a["in_place"] == run_b["in_place"]
    assert run_a["log_structured"] == run_b["log_structured"]
