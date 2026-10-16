"""
Flash File System Strategies: In-Place Updates vs. Log-Structured Writes.

Contains:
1. InPlaceFS: Baseline strategy with fixed direct 1:1 mapping (LBA = PPA).
   In-place updates require reading the containing segment, erasing it,
   and rewriting all valid pages along with the updated page.
2. LogStructuredFS: F2FS-inspired log-structured append strategy.
   Writes append sequentially to free pages, invalidating old pages.
   Maintains logical-to-physical mapping tables and triggers garbage collection
   when free space is low.
"""

from typing import Any, Dict, List, Optional
from flash import FlashDevice, PageState
from metrics import MetricsTracker
from garbage_collector import GarbageCollector


class InPlaceFS:
    """
    In-Place update baseline flash filesystem.
    Fixed direct 1:1 mapping between LBA and PPA (PPA = LBA).
    Updating a page requires erasing its segment and rewriting valid pages.
    """

    def __init__(self, flash: FlashDevice, metrics: Optional[MetricsTracker] = None) -> None:
        self.flash: FlashDevice = flash
        self.metrics: MetricsTracker = metrics or MetricsTracker()
        self.max_lba: int = flash.total_pages

    def write(self, lba: int, data: Any) -> None:
        """
        Writes data to logical block address (LBA).
        If the target page is FREE, writes directly.
        If already VALID (an update), reads the segment, erases it, and rewrites.
        """
        if not (isinstance(lba, int) and 0 <= lba < self.max_lba):
            raise IndexError(f"LBA {lba} out of range [0, {self.max_lba - 1}].")

        ppa = lba
        seg_id, _ = self.flash.ppa_to_seg_offset(ppa)
        target_page = self.flash.get_page(ppa)

        if target_page.state == PageState.FREE:
            # Cold write / first write to this page
            self.flash.write_page(ppa, data, lba)
            self.metrics.record_logical_write()
            self.metrics.record_physical_write(1)
        else:
            # In-place update: read segment, update data in buffer, erase segment, rewrite all valid pages
            segment = self.flash.segments[seg_id]
            buffer: Dict[int, Any] = {}

            for page in segment.pages:
                if page.state == PageState.VALID:
                    buffer[page.ppa] = (page.data, page.lba)

            # Update target page in buffer
            buffer[ppa] = (data, lba)

            # Erase segment
            self.flash.erase_segment(seg_id)
            self.metrics.record_segment_erase(1)

            # Rewrite all valid pages back to the segment
            for page_ppa, (page_data, page_lba) in buffer.items():
                self.flash.write_page(page_ppa, page_data, page_lba)
                self.metrics.record_physical_write(1)

            self.metrics.record_logical_write()

    def read(self, lba: int) -> Optional[Any]:
        """Reads data for the given LBA."""
        if not (isinstance(lba, int) and 0 <= lba < self.max_lba):
            raise IndexError(f"LBA {lba} out of range [0, {self.max_lba - 1}].")
        ppa = lba
        state, data, _ = self.flash.read_page(ppa)
        if state == PageState.VALID:
            return data
        return None


class LogStructuredFS:
    """
    Log-Structured flash filesystem (F2FS-inspired).
    Writes append sequentially to free pages in an active segment.
    Maintains L2P (logical-to-physical) and P2L (physical-to-logical) mapping tables.
    Enforces over-provisioning reserve to guarantee space for GC page migration.
    Triggers greedy garbage collection when free space is low.
    """

    def __init__(
        self,
        flash: FlashDevice,
        metrics: Optional[MetricsTracker] = None,
        min_free_segments: int = 1,
        max_lba: Optional[int] = None,
    ) -> None:
        if min_free_segments < 1 or min_free_segments >= flash.num_segments:
            raise ValueError(
                f"min_free_segments must be between 1 and {flash.num_segments - 1}, "
                f"got {min_free_segments}."
            )
        self.flash: FlashDevice = flash
        self.metrics: MetricsTracker = metrics or MetricsTracker()
        self.min_free_segments: int = min_free_segments
        self.reserved_segments: int = min_free_segments
        self.max_usable_pages: int = (flash.num_segments - self.reserved_segments) * flash.pages_per_segment
        self.max_lba: int = max_lba if max_lba is not None else flash.total_pages
        self.gc: GarbageCollector = GarbageCollector(self)

        # Mapping tables
        self.l2p: Dict[int, int] = {}  # LBA -> PPA
        self.p2l: Dict[int, int] = {}  # PPA -> LBA

        # Active segment and write pointer
        self.active_segment_id: Optional[int] = None
        self.active_page_offset: int = 0
        self.is_gc_in_progress: bool = False

    def get_free_segment_ids(self) -> List[int]:
        """Returns list of segment IDs that are completely FREE (excluding active segment)."""
        return [
            seg.segment_id
            for seg in self.flash.segments
            if seg.segment_id != self.active_segment_id and seg.free_count == self.flash.pages_per_segment
        ]

    def _ensure_active_segment(self) -> None:
        """
        Ensures that an active write segment with available free pages is ready.
        If the active segment is full or None:
        1. Triggers GC if free segments are at or below reserve threshold.
        2. Activates a clean free segment from the pool.
        3. Raises RuntimeError if no free segment can be obtained.
        """
        if self.active_segment_id is not None and self.active_page_offset < self.flash.pages_per_segment:
            return

        self.active_segment_id = None
        free_segs = self.get_free_segment_ids()

        if len(free_segs) <= self.min_free_segments and not self.is_gc_in_progress:
            # Activate a free segment to receive any migrated pages during GC
            if free_segs:
                self.active_segment_id = free_segs.pop(0)
                self.active_page_offset = 0

            # Trigger GC if invalid pages exist and free segments are still below reserve
            while len(self.get_free_segment_ids()) < self.min_free_segments and self.flash.total_invalid_pages > 0:
                self.is_gc_in_progress = True
                try:
                    reclaimed = self.gc.collect()
                    if reclaimed == 0 and self.gc.select_victim_segment() is None:
                        break
                finally:
                    self.is_gc_in_progress = False

        if self.active_segment_id is None:
            free_segs = self.get_free_segment_ids()
            if not free_segs:
                if not self.is_gc_in_progress and self.flash.total_invalid_pages > 0:
                    self.is_gc_in_progress = True
                    try:
                        self.gc.collect()
                    finally:
                        self.is_gc_in_progress = False
                    free_segs = self.get_free_segment_ids()

            if not free_segs:
                raise RuntimeError("Flash storage is completely full; GC cannot reclaim pages.")

            self.active_segment_id = free_segs.pop(0)
            self.active_page_offset = 0

    def allocate_page(self) -> int:
        """Allocates next sequential free page."""
        self._ensure_active_segment()
        ppa = self.flash.seg_offset_to_ppa(self.active_segment_id, self.active_page_offset)
        self.active_page_offset += 1
        return ppa

    def allocate_free_page_for_gc(self) -> int:
        """Allocates a free page specifically during GC page migration."""
        return self.allocate_page()

    def write(self, lba: int, data: Any) -> None:
        """
        Log-structured write:
        1. Validates LBA range and capacity limits.
        2. Allocates next sequential free page (running GC if needed).
        3. Writes data safely before modifying existing state.
        4. Invalidates previous physical page and cleans up reverse mapping.
        5. Updates L2P and P2L mappings and records metrics.
        """
        if not (isinstance(lba, int) and 0 <= lba < self.max_lba):
            raise IndexError(f"LBA {lba} out of range [0, {self.max_lba - 1}].")

        is_update = lba in self.l2p
        if not is_update and len(self.l2p) >= self.max_usable_pages:
            raise RuntimeError(
                f"Storage capacity exceeded: device has reached maximum usable capacity ({self.max_usable_pages} blocks) "
                f"with {self.reserved_segments} segment(s) reserved for over-provisioning/GC."
            )

        new_ppa = self.allocate_page()
        try:
            self.flash.write_page(new_ppa, data, lba)
        except Exception:
            # If writing failed, do not alter mappings or invalidate old page
            raise

        old_ppa = self.l2p.get(lba)
        if old_ppa is not None:
            self.flash.invalidate_page(old_ppa)
            if old_ppa in self.p2l:
                del self.p2l[old_ppa]

        self.l2p[lba] = new_ppa
        self.p2l[new_ppa] = lba

        self.metrics.record_logical_write()
        self.metrics.record_physical_write(1)

    def read(self, lba: int) -> Optional[Any]:
        """Reads data for the given LBA using the L2P mapping table."""
        if not (isinstance(lba, int) and 0 <= lba < self.max_lba):
            raise IndexError(f"LBA {lba} out of range [0, {self.max_lba - 1}].")
        ppa = self.l2p.get(lba)
        if ppa is None:
            return None
        state, data, _ = self.flash.read_page(ppa)
        if state == PageState.VALID:
            return data
        return None
