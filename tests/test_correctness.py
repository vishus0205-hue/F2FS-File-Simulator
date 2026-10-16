"""
Comprehensive correctness tests for F2FS-inspired Flash Storage Simulator.

Tests cover:
1. Reverse mapping (p2l) consistency and cleanup during updates and GC.
2. Data preservation and mapping integrity across multiple GC cycles.
3. Near-full storage and over-provisioning capacity limits.
4. Failed-write safety and atomic update preservation.
5. Strict validation of logical block addresses (LBAs).
6. Deterministic reproducibility across repeated runs.
"""

import pytest
from flash import FlashDevice, PageState
from filesystem import LogStructuredFS, InPlaceFS
from metrics import MetricsTracker
from workloads import generate_workload, populate_initial_data
import experiments


def assert_bidirectional_mapping_consistency(fs: LogStructuredFS, flash: FlashDevice):
    """
    Core correctness invariant:
    - len(p2l) must equal len(l2p) and flash.total_valid_pages.
    - Every entry in p2l must map to a VALID page on flash with matching LBA.
    - Every entry in l2p must map to a VALID page on flash with matching PPA.
    - No PPA in FREE or INVALID state can appear in p2l.
    """
    assert len(fs.p2l) == len(fs.l2p)
    assert len(fs.p2l) == flash.total_valid_pages

    # Check forward mapping (L2P)
    for lba, ppa in fs.l2p.items():
        assert fs.p2l.get(ppa) == lba
        state, _, page_lba = flash.read_page(ppa)
        assert state == PageState.VALID
        assert page_lba == lba

    # Check reverse mapping (P2L)
    for ppa, lba in fs.p2l.items():
        assert fs.l2p.get(lba) == ppa
        state, _, page_lba = flash.read_page(ppa)
        assert state == PageState.VALID
        assert page_lba == lba

    # Ensure no FREE or INVALID physical pages are present in p2l
    for seg in flash.segments:
        for page in seg.pages:
            if page.state in (PageState.FREE, PageState.INVALID):
                assert page.ppa not in fs.p2l, (
                    f"Inconsistency: PPA {page.ppa} is {page.state.value} on flash but still present in p2l!"
                )


# ==============================================================================
# 1. Reverse Mapping Consistency Tests
# ==============================================================================

def test_reverse_mapping_removed_on_update():
    """When an LBA is overwritten, its previous PPA must be removed from p2l."""
    flash = FlashDevice(num_segments=3, pages_per_segment=4)
    fs = LogStructuredFS(flash)

    fs.write(0, "val_0_first")
    ppa_first = fs.l2p[0]
    assert fs.p2l[ppa_first] == 0
    assert_bidirectional_mapping_consistency(fs, flash)

    # Overwrite LBA 0
    fs.write(0, "val_0_second")
    ppa_second = fs.l2p[0]
    assert ppa_second != ppa_first
    assert ppa_first not in fs.p2l
    assert fs.p2l[ppa_second] == 0
    assert_bidirectional_mapping_consistency(fs, flash)


def test_reverse_mapping_purged_on_segment_erase_in_gc():
    """All PPAs of an erased victim segment must be purged from p2l after GC."""
    flash = FlashDevice(num_segments=3, pages_per_segment=4)
    fs = LogStructuredFS(flash)

    # Fill segment 0 (LBAs 0..3)
    for lba in range(4):
        fs.write(lba, f"v1_{lba}")

    # Overwrite LBAs 0, 1, 2 into segment 1 -> old PPAs 0, 1, 2 become INVALID
    fs.write(0, "v2_0")
    fs.write(1, "v2_1")
    fs.write(2, "v2_2")

    # Before GC: segment 0 has 3 invalid pages (0, 1, 2) and 1 valid page (3)
    # Trigger GC
    fs.gc.collect()

    # Segment 0 was the victim and is now fully erased (all pages FREE)
    for ppa in range(4):
        assert ppa not in fs.p2l
        assert flash.get_page(ppa).state == PageState.FREE

    assert_bidirectional_mapping_consistency(fs, flash)


def test_reverse_mapping_consistency_under_extended_workload():
    """Repeated updates and GC cycles must maintain strict bi-directional mapping consistency."""
    flash = FlashDevice(num_segments=6, pages_per_segment=8)
    fs = LogStructuredFS(flash)
    num_blocks = 30
    populate_initial_data(fs, num_blocks)

    workload = generate_workload("skewed", num_blocks, 200, seed=77)
    for op, lba in enumerate(workload):
        fs.write(lba, f"data_op_{op}")
        if op % 20 == 0:
            assert_bidirectional_mapping_consistency(fs, flash)

    assert_bidirectional_mapping_consistency(fs, flash)


# ==============================================================================
# 2. Data Preservation during GC
# ==============================================================================

def test_gc_preserves_all_data_across_many_cycles():
    """Verify that multiple continuous GC cycles never corrupt or drop stored data."""
    flash = FlashDevice(num_segments=6, pages_per_segment=16)
    metrics = MetricsTracker()
    fs = LogStructuredFS(flash, metrics)
    num_blocks = 60

    expected = {}
    for lba in range(num_blocks):
        fs.write(lba, f"initial_{lba}")
        expected[lba] = f"initial_{lba}"

    metrics.start_measuring()
    workload = generate_workload("uniform", num_blocks, 500, seed=42)
    for op, lba in enumerate(workload):
        val = f"up_{op}_lba{lba}"
        fs.write(lba, val)
        expected[lba] = val

    metrics.stop_measuring()
    assert metrics.gc_runs > 5

    # Verify all blocks match expected data exactly
    for lba in range(num_blocks):
        assert fs.read(lba) == expected[lba]

    assert_bidirectional_mapping_consistency(fs, flash)


# ==============================================================================
# 3. Near-Full Storage & Over-Provisioning Reserve Tests
# ==============================================================================

def test_over_provisioning_reserve_enforced_for_cold_writes():
    """Cold writes exceeding maximum usable capacity reserved for OP must be rejected."""
    # 4 segments, 4 pages/seg = 16 pages total. min_free_segments = 1 -> max_usable = 12 pages
    flash = FlashDevice(num_segments=4, pages_per_segment=4)
    fs = LogStructuredFS(flash, min_free_segments=1)
    assert fs.max_usable_pages == 12

    # Write up to usable capacity (12 distinct blocks)
    for lba in range(12):
        fs.write(lba, f"init_{lba}")

    assert len(fs.l2p) == 12

    # Attempting to write a 13th new block must raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        fs.write(12, "exceeding_block")
    assert "Storage capacity exceeded" in str(exc_info.value)


def test_updates_allowed_when_storage_is_at_usable_capacity():
    """Even when at 100% usable capacity, updates to existing LBAs must succeed through GC."""
    flash = FlashDevice(num_segments=4, pages_per_segment=8)  # 32 pages, usable = 24 pages
    fs = LogStructuredFS(flash, min_free_segments=1)
    usable_blocks = fs.max_usable_pages

    # Fill to maximum usable capacity
    for lba in range(usable_blocks):
        fs.write(lba, f"val_{lba}")

    # Heavy updates to existing blocks (triggering multiple GCs near capacity)
    for op in range(100):
        target_lba = op % usable_blocks
        fs.write(target_lba, f"updated_val_{op}")
        assert fs.read(target_lba) == f"updated_val_{op}"

    assert_bidirectional_mapping_consistency(fs, flash)


# ==============================================================================
# 4. Failed-Write Safety & Atomic Update Preservation
# ==============================================================================

def test_write_failure_preserves_existing_data_and_mappings():
    """If a write fails during physical writing, old data and mappings must remain intact."""
    flash = FlashDevice(num_segments=4, pages_per_segment=4)
    fs = LogStructuredFS(flash)

    # Initial write to LBA 2
    fs.write(2, "original_data")
    old_ppa = fs.l2p[2]
    assert fs.read(2) == "original_data"

    # Monkey-patch flash.write_page to simulate a hardware write fault
    real_write_page = flash.write_page

    def faulty_write_page(ppa, data, lba):
        raise IOError("Simulated physical write failure")

    flash.write_page = faulty_write_page

    with pytest.raises(IOError):
        fs.write(2, "corrupted_attempt")

    # Restore write_page
    flash.write_page = real_write_page

    # Verify that existing mapping and data at LBA 2 are completely unharmed
    assert fs.l2p[2] == old_ppa
    assert fs.p2l[old_ppa] == 2
    state, data, mapped_lba = flash.read_page(old_ppa)
    assert state == PageState.VALID
    assert data == "original_data"
    assert mapped_lba == 2
    assert fs.read(2) == "original_data"
    assert_bidirectional_mapping_consistency(fs, flash)


# ==============================================================================
# 5. LBA Validation Tests
# ==============================================================================

def test_log_structured_rejects_invalid_lba():
    """LogStructuredFS must reject negative, out-of-range, and non-integer LBAs."""
    flash = FlashDevice(num_segments=4, pages_per_segment=4)
    fs = LogStructuredFS(flash)

    # Negative LBA
    with pytest.raises(IndexError):
        fs.write(-1, "bad")
    with pytest.raises(IndexError):
        fs.read(-1)

    # Out-of-range LBA (>= max_lba)
    with pytest.raises(IndexError):
        fs.write(flash.total_pages, "bad")
    with pytest.raises(IndexError):
        fs.read(flash.total_pages)

    # Non-integer LBA
    with pytest.raises(IndexError):
        fs.write("0", "bad")
    with pytest.raises(IndexError):
        fs.read("0")


def test_inplace_rejects_invalid_lba():
    """InPlaceFS must reject negative, out-of-range, and non-integer LBAs."""
    flash = FlashDevice(num_segments=4, pages_per_segment=4)
    fs = InPlaceFS(flash)

    with pytest.raises(IndexError):
        fs.write(-1, "bad")
    with pytest.raises(IndexError):
        fs.read(-1)

    with pytest.raises(IndexError):
        fs.write(16, "bad")
    with pytest.raises(IndexError):
        fs.read(16)

    with pytest.raises(IndexError):
        fs.write("0", "bad")
    with pytest.raises(IndexError):
        fs.read("0")


# ==============================================================================
# 6. Deterministic Reproducibility
# ==============================================================================

def test_experiments_deterministic_reproducibility():
    """Running identical experiments with identical seeds must yield identical results."""
    run1 = experiments.run_strategy_comparison(num_segments=8, pages_per_segment=16, num_updates=250, seed=555)
    run2 = experiments.run_strategy_comparison(num_segments=8, pages_per_segment=16, num_updates=250, seed=555)
    assert run1 == run2

    run_util1 = experiments.run_utilization_experiment(num_segments=8, pages_per_segment=16, utilizations=(0.5, 0.8), num_updates=200, seed=888)
    run_util2 = experiments.run_utilization_experiment(num_segments=8, pages_per_segment=16, utilizations=(0.5, 0.8), num_updates=200, seed=888)
    assert run_util1 == run_util2
