"""
Garbage Collector for Log-Structured Flash Storage.

Implements the Greedy Garbage Collection policy:
- Selects the victim segment with the fewest valid pages (highest reclaimable space).
- Migrates valid pages from the victim segment to new free pages sequentially.
- Erases the victim segment, resetting all its pages to FREE.
- Updates logical-to-physical mappings to ensure consistency without data loss.
"""

from typing import List, Optional, TYPE_CHECKING
from flash import PageState

if TYPE_CHECKING:
    from filesystem import LogStructuredFS


class GarbageCollector:
    """Greedy garbage collector for flash memory segments."""

    def __init__(self, fs: "LogStructuredFS") -> None:
        self.fs = fs

    def select_victim_segment(self) -> Optional[int]:
        """
        Greedy policy: select the segment with the fewest valid pages.
        Excludes the currently active write segment and completely free segments.
        Prefers segments with invalid pages to actually reclaim space.
        """
        best_segment_id: Optional[int] = None
        min_valid: int = self.fs.flash.pages_per_segment + 1
        max_invalid: int = -1

        for seg in self.fs.flash.segments:
            seg_id = seg.segment_id
            # Do not reclaim the active write segment
            if seg_id == self.fs.active_segment_id:
                continue

            # Skip segments that are already completely FREE
            if seg.free_count == self.fs.flash.pages_per_segment:
                continue

            # Must contain at least one invalid page to reclaim space
            if seg.invalid_count == 0:
                continue

            valid = seg.valid_count
            invalid = seg.invalid_count

            # Minimize valid pages, tie-break by maximizing invalid pages
            if valid < min_valid or (valid == min_valid and invalid > max_invalid):
                min_valid = valid
                max_invalid = invalid
                best_segment_id = seg_id

        return best_segment_id

    def collect(self) -> int:
        """
        Performs a single round of garbage collection:
        1. Selects victim segment with minimum valid pages.
        2. Copies valid pages to free pages.
        3. Erases the victim segment.
        4. Updates mappings.
        Returns the number of valid pages copied.
        """
        victim_id = self.select_victim_segment()
        if victim_id is None:
            # Fallback: check if any non-active segment has invalid pages
            return 0

        victim_seg = self.fs.flash.segments[victim_id]
        pages_to_migrate: List[int] = []

        # Find all valid pages in the victim segment
        for page in victim_seg.pages:
            if page.state == PageState.VALID:
                pages_to_migrate.append(page.ppa)

        pages_copied = 0
        for old_ppa in pages_to_migrate:
            _, data, lba = self.fs.flash.read_page(old_ppa)
            if lba is None:
                continue

            # Verify that mapping still points to this old_ppa
            if self.fs.l2p.get(lba) != old_ppa:
                continue

            # Allocate new free page and write migrated data
            new_ppa = self.fs.allocate_free_page_for_gc()
            self.fs.flash.write_page(new_ppa, data, lba)

            # Update mappings
            self.fs.l2p[lba] = new_ppa
            self.fs.p2l[new_ppa] = lba
            if old_ppa in self.fs.p2l:
                del self.fs.p2l[old_ppa]

            pages_copied += 1

        # Clean up all remaining reverse mappings for the victim segment before erase
        for page in victim_seg.pages:
            if page.ppa in self.fs.p2l:
                del self.fs.p2l[page.ppa]

        # Erase the victim segment
        self.fs.flash.erase_segment(victim_id)

        # Notify metrics tracker
        self.fs.metrics.record_gc(pages_copied)

        return pages_copied
