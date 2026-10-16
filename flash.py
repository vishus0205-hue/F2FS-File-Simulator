"""
Flash Memory Device Simulation.

Simulates flash physical characteristics:
- Pages have three states: FREE, VALID, INVALID.
- Out-of-place writes: non-free pages cannot be overwritten directly without an erase.
- Erases happen at segment granularity, resetting pages to FREE and incrementing erase counts.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class PageState(str, Enum):
    FREE = "FREE"
    VALID = "VALID"
    INVALID = "INVALID"


class Page:
    """Represents a single physical flash page."""

    def __init__(self, ppa: int) -> None:
        self.ppa: int = ppa
        self.state: PageState = PageState.FREE
        self.data: Any = None
        self.lba: Optional[int] = None  # Logical block address mapped to this page

    def reset(self) -> None:
        """Resets page to FREE state upon segment erase."""
        self.state = PageState.FREE
        self.data = None
        self.lba = None

    def __repr__(self) -> str:
        return f"Page(ppa={self.ppa}, state={self.state.value}, lba={self.lba})"


class Segment:
    """Represents a flash segment (erase block) containing multiple pages."""

    def __init__(self, segment_id: int, pages_per_segment: int) -> None:
        self.segment_id: int = segment_id
        self.pages_per_segment: int = pages_per_segment
        self.erase_count: int = 0
        base_ppa = segment_id * pages_per_segment
        self.pages: List[Page] = [Page(base_ppa + offset) for offset in range(pages_per_segment)]

    def erase(self) -> None:
        """Erases the segment, resetting all pages to FREE and incrementing erase count."""
        self.erase_count += 1
        for page in self.pages:
            page.reset()

    @property
    def valid_count(self) -> int:
        return sum(1 for p in self.pages if p.state == PageState.VALID)

    @property
    def invalid_count(self) -> int:
        return sum(1 for p in self.pages if p.state == PageState.INVALID)

    @property
    def free_count(self) -> int:
        return sum(1 for p in self.pages if p.state == PageState.FREE)


class FlashDevice:
    """Simulates a flash storage device composed of segments and pages."""

    def __init__(self, num_segments: int = 32, pages_per_segment: int = 64) -> None:
        if num_segments <= 0 or pages_per_segment <= 0:
            raise ValueError("num_segments and pages_per_segment must be positive integers.")
        self.num_segments: int = num_segments
        self.pages_per_segment: int = pages_per_segment
        self.total_pages: int = num_segments * pages_per_segment
        self.segments: List[Segment] = [
            Segment(seg_id, pages_per_segment) for seg_id in range(num_segments)
        ]

    def ppa_to_seg_offset(self, ppa: int) -> Tuple[int, int]:
        """Converts physical page address (PPA) to (segment_id, page_offset)."""
        if not (0 <= ppa < self.total_pages):
            raise IndexError(f"PPA {ppa} out of range [0, {self.total_pages - 1}].")
        seg_id = ppa // self.pages_per_segment
        offset = ppa % self.pages_per_segment
        return seg_id, offset

    def seg_offset_to_ppa(self, segment_id: int, page_offset: int) -> int:
        """Converts (segment_id, page_offset) to physical page address (PPA)."""
        if not (0 <= segment_id < self.num_segments):
            raise IndexError(f"segment_id {segment_id} out of range [0, {self.num_segments - 1}].")
        if not (0 <= page_offset < self.pages_per_segment):
            raise IndexError(f"page_offset {page_offset} out of range [0, {self.pages_per_segment - 1}].")
        return segment_id * self.pages_per_segment + page_offset

    def get_page(self, ppa: int) -> Page:
        seg_id, offset = self.ppa_to_seg_offset(ppa)
        return self.segments[seg_id].pages[offset]

    def read_page(self, ppa: int) -> Tuple[PageState, Any, Optional[int]]:
        """Reads page state, data, and logical block address."""
        page = self.get_page(ppa)
        return page.state, page.data, page.lba

    def write_page(self, ppa: int, data: Any, lba: Optional[int]) -> None:
        """
        Writes data to a physical page.
        Raises RuntimeError if the page is not in FREE state (no direct overwrite).
        """
        page = self.get_page(ppa)
        if page.state != PageState.FREE:
            raise RuntimeError(
                f"Flash write violation: PPA {ppa} is {page.state.value}, not FREE. "
                "Flash memory does not support direct overwrites without an erase."
            )
        page.state = PageState.VALID
        page.data = data
        page.lba = lba

    def invalidate_page(self, ppa: int) -> None:
        """Marks a VALID page as INVALID."""
        page = self.get_page(ppa)
        if page.state == PageState.FREE:
            raise RuntimeError(f"Cannot invalidate a FREE page at PPA {ppa}.")
        page.state = PageState.INVALID

    def erase_segment(self, segment_id: int) -> None:
        """Erases the specified segment."""
        if not (0 <= segment_id < self.num_segments):
            raise IndexError(f"segment_id {segment_id} out of range [0, {self.num_segments - 1}].")
        self.segments[segment_id].erase()

    # Device-wide summary properties
    @property
    def total_erases(self) -> int:
        return sum(seg.erase_count for seg in self.segments)

    @property
    def total_valid_pages(self) -> int:
        return sum(seg.valid_count for seg in self.segments)

    @property
    def total_invalid_pages(self) -> int:
        return sum(seg.invalid_count for seg in self.segments)

    @property
    def total_free_pages(self) -> int:
        return sum(seg.free_count for seg in self.segments)
