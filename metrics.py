"""
Metrics tracking for Flash Storage Simulator.

Tracks logical writes, physical page writes, segment erases, GC invocations,
and pages copied during GC. Calculates Write Amplification Factor (WAF).
Initialization writes are explicitly excluded from WAF calculations.
"""

from typing import Any, Dict


class MetricsTracker:
    """Tracks performance and wear metrics during simulation runs."""

    def __init__(self) -> None:
        self.is_measuring: bool = False

        # Workload metrics (excluded from initialization)
        self.logical_writes: int = 0
        self.physical_writes: int = 0
        self.segment_erases: int = 0
        self.gc_runs: int = 0
        self.gc_pages_copied: int = 0

        # Initialization metrics (for auditing)
        self.init_logical_writes: int = 0
        self.init_physical_writes: int = 0
        self.init_segment_erases: int = 0

    def start_measuring(self) -> None:
        """Call after initialization to start tracking workload metrics."""
        self.is_measuring = True

    def stop_measuring(self) -> None:
        """Stops measuring workload metrics."""
        self.is_measuring = False

    def record_logical_write(self) -> None:
        if self.is_measuring:
            self.logical_writes += 1
        else:
            self.init_logical_writes += 1

    def record_physical_write(self, count: int = 1) -> None:
        if self.is_measuring:
            self.physical_writes += count
        else:
            self.init_physical_writes += count

    def record_segment_erase(self, count: int = 1) -> None:
        if self.is_measuring:
            self.segment_erases += count
        else:
            self.init_segment_erases += count

    def record_gc(self, pages_copied: int) -> None:
        if self.is_measuring:
            self.gc_runs += 1
            self.gc_pages_copied += pages_copied
            # Each copied page is written to a new free page
            self.physical_writes += pages_copied
            self.segment_erases += 1
        else:
            self.init_physical_writes += pages_copied
            self.init_segment_erases += 1

    @property
    def waf(self) -> float:
        """
        Write Amplification Factor:
        WAF = Total physical page writes / Logical writes (excluding initialization).
        """
        if self.logical_writes == 0:
            return 0.0
        return self.physical_writes / self.logical_writes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logical_writes": self.logical_writes,
            "physical_writes": self.physical_writes,
            "waf": round(self.waf, 4),
            "segment_erases": self.segment_erases,
            "gc_runs": self.gc_runs,
            "gc_pages_copied": self.gc_pages_copied,
        }

    def summary(self) -> str:
        return (
            f"Logical Writes:         {self.logical_writes}\n"
            f"Physical Page Writes:   {self.physical_writes}\n"
            f"Write Amplification:    {self.waf:.4f}\n"
            f"Segment Erases:         {self.segment_erases}\n"
            f"GC Invocations:         {self.gc_runs}\n"
            f"Pages Copied in GC:     {self.gc_pages_copied}"
        )
