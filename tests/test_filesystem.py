"""
Unit tests for InPlaceFS and LogStructuredFS filesystems (filesystem.py).
"""

from flash import FlashDevice, PageState
from filesystem import InPlaceFS, LogStructuredFS
from metrics import MetricsTracker


def test_inplace_cold_write_and_read():
    flash = FlashDevice(num_segments=2, pages_per_segment=4)
    metrics = MetricsTracker()
    fs = InPlaceFS(flash, metrics)
    metrics.start_measuring()

    fs.write(lba=0, data="data_0")
    fs.write(lba=1, data="data_1")

    assert fs.read(0) == "data_0"
    assert fs.read(1) == "data_1"
    assert metrics.logical_writes == 2
    assert metrics.physical_writes == 2
    assert metrics.segment_erases == 0


def test_inplace_update_triggers_erase_and_rewrites():
    flash = FlashDevice(num_segments=2, pages_per_segment=4)
    metrics = MetricsTracker()
    fs = InPlaceFS(flash, metrics)

    # Initial population of segment 0 (4 pages)
    for lba in range(4):
        fs.write(lba, f"initial_{lba}")

    metrics.start_measuring()
    # Update LBA 1
    fs.write(1, "updated_1")

    assert fs.read(1) == "updated_1"
    assert fs.read(0) == "initial_0"
    assert fs.read(2) == "initial_2"
    assert fs.read(3) == "initial_3"

    assert metrics.logical_writes == 1
    # Segment erase occurs: 1 erase, and all 4 valid pages rewritten
    assert metrics.segment_erases == 1
    assert metrics.physical_writes == 4
    assert metrics.waf == 4.0


def test_log_structured_append_and_invalidate():
    flash = FlashDevice(num_segments=4, pages_per_segment=4)
    metrics = MetricsTracker()
    fs = LogStructuredFS(flash, metrics)
    metrics.start_measuring()

    fs.write(lba=0, data="first_val")
    ppa_first = fs.l2p[0]
    assert ppa_first == 0

    # Overwrite LBA 0
    fs.write(lba=0, data="second_val")
    ppa_second = fs.l2p[0]

    # Verify out-of-place sequential write
    assert ppa_second == 1
    # Old page at PPA 0 is marked INVALID
    state_old, _, _ = flash.read_page(ppa_first)
    assert state_old == PageState.INVALID

    # New page at PPA 1 is VALID
    state_new, data_new, _ = flash.read_page(ppa_second)
    assert state_new == PageState.VALID
    assert data_new == "second_val"
    assert fs.read(0) == "second_val"

    assert metrics.logical_writes == 2
    assert metrics.physical_writes == 2
    assert metrics.waf == 1.0
