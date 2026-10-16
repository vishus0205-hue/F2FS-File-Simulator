"""
Unit tests for flash device simulation (flash.py).
"""

import pytest
from flash import FlashDevice, PageState


def test_flash_initialization():
    flash = FlashDevice(num_segments=4, pages_per_segment=8)
    assert flash.num_segments == 4
    assert flash.pages_per_segment == 8
    assert flash.total_pages == 32
    assert flash.total_free_pages == 32
    assert flash.total_valid_pages == 0
    assert flash.total_invalid_pages == 0
    assert flash.total_erases == 0


def test_write_and_read_page():
    flash = FlashDevice(num_segments=2, pages_per_segment=4)
    ppa = 0
    flash.write_page(ppa, "test_data", lba=10)

    state, data, lba = flash.read_page(ppa)
    assert state == PageState.VALID
    assert data == "test_data"
    assert lba == 10
    assert flash.total_free_pages == 7
    assert flash.total_valid_pages == 1


def test_overwrite_non_free_page_raises_error():
    flash = FlashDevice(num_segments=2, pages_per_segment=4)
    ppa = 3
    flash.write_page(ppa, "first_write", lba=5)

    # Attempting to write again directly to the valid page must fail
    with pytest.raises(RuntimeError) as exc_info:
        flash.write_page(ppa, "second_write", lba=5)
    assert "Flash write violation" in str(exc_info.value)


def test_invalidate_page():
    flash = FlashDevice(num_segments=2, pages_per_segment=4)
    ppa = 2
    flash.write_page(ppa, "some_data", lba=1)
    flash.invalidate_page(ppa)

    state, _, _ = flash.read_page(ppa)
    assert state == PageState.INVALID

    # Invalidate FREE page should raise error
    with pytest.raises(RuntimeError):
        flash.invalidate_page(0)


def test_segment_erase():
    flash = FlashDevice(num_segments=2, pages_per_segment=4)
    # Write to all pages in segment 0
    for ppa in range(4):
        flash.write_page(ppa, f"val_{ppa}", lba=ppa)

    assert flash.segments[0].valid_count == 4
    assert flash.segments[0].erase_count == 0

    flash.erase_segment(0)

    assert flash.segments[0].erase_count == 1
    assert flash.segments[0].valid_count == 0
    assert flash.segments[0].free_count == 4
    for ppa in range(4):
        state, data, lba = flash.read_page(ppa)
        assert state == PageState.FREE
        assert data is None
        assert lba is None


def test_invalid_ppa_and_segment_index():
    flash = FlashDevice(num_segments=2, pages_per_segment=4)
    with pytest.raises(IndexError):
        flash.read_page(100)
    with pytest.raises(IndexError):
        flash.erase_segment(5)
