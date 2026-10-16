"""
Unit tests for Garbage Collector (garbage_collector.py).
"""

from flash import FlashDevice, PageState
from filesystem import LogStructuredFS
from metrics import MetricsTracker


def test_greedy_victim_selection():
    # 4 segments, 4 pages per segment
    flash = FlashDevice(num_segments=4, pages_per_segment=4)
    fs = LogStructuredFS(flash, MetricsTracker())

    # Segment 0: 1 valid, 3 invalid
    for offset in range(4):
        ppa = flash.seg_offset_to_ppa(0, offset)
        flash.write_page(ppa, f"data_{offset}", lba=offset)
    # Invalidate 3 pages in seg 0
    flash.invalidate_page(flash.seg_offset_to_ppa(0, 1))
    flash.invalidate_page(flash.seg_offset_to_ppa(0, 2))
    flash.invalidate_page(flash.seg_offset_to_ppa(0, 3))
    fs.l2p[0] = 0
    fs.p2l[0] = 0

    # Segment 1: 3 valid, 1 invalid
    for offset in range(4):
        ppa = flash.seg_offset_to_ppa(1, offset)
        flash.write_page(ppa, f"data_1_{offset}", lba=10 + offset)
    flash.invalidate_page(flash.seg_offset_to_ppa(1, 0))
    fs.l2p[11] = flash.seg_offset_to_ppa(1, 1)
    fs.l2p[12] = flash.seg_offset_to_ppa(1, 2)
    fs.l2p[13] = flash.seg_offset_to_ppa(1, 3)

    # Active segment is segment 2
    fs.active_segment_id = 2

    # Greedy policy must pick segment 0 because it has only 1 valid page vs 3 valid pages in seg 1
    victim = fs.gc.select_victim_segment()
    assert victim == 0


def test_garbage_collection_cleans_and_migrates():
    flash = FlashDevice(num_segments=3, pages_per_segment=4)
    metrics = MetricsTracker()
    fs = LogStructuredFS(flash, metrics)
    metrics.start_measuring()

    # Fill segment 0 (LBA 0..3)
    for lba in range(4):
        fs.write(lba, f"v1_{lba}")

    # Overwrite LBA 0, 1, 2 -> Written to segment 1, segment 0 has 3 invalid, 1 valid (LBA 3)
    fs.write(0, "v2_0")
    fs.write(1, "v2_1")
    fs.write(2, "v2_2")

    assert flash.segments[0].invalid_count == 3
    assert flash.segments[0].valid_count == 1

    # Run GC
    copied = fs.gc.collect()

    assert copied == 1
    # Segment 0 was victim, now fully erased
    assert flash.segments[0].erase_count == 1
    assert flash.segments[0].free_count == 4
    assert flash.segments[0].valid_count == 0

    # LBA 3 was migrated and is still readable
    assert fs.read(3) == "v1_3"
    assert fs.read(0) == "v2_0"
    assert fs.read(1) == "v2_1"
    assert fs.read(2) == "v2_2"

    assert metrics.gc_runs == 1
    assert metrics.gc_pages_copied == 1
