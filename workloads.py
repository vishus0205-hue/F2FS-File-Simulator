"""
Workload Generators for Flash Storage Simulator.

Generates reproducible access patterns:
- Uniform: Every logical block address has an equal probability of being updated.
- Skewed (80/20 Rule): 20% of logical blocks receive ~80% of updates (hot blocks),
  while the remaining 80% receive ~20% (cold blocks).
"""

import random
from typing import List, Union
from filesystem import InPlaceFS, LogStructuredFS


def generate_workload(
    workload_type: str,
    num_blocks: int,
    num_operations: int,
    seed: int = 42,
) -> List[int]:
    """
    Generates a list of logical block addresses to update.

    Args:
        workload_type: 'uniform' or 'skewed'
        num_blocks: Total active logical blocks in the workload
        num_operations: Number of write/update operations to generate
        seed: Random seed for reproducible workload generation

    Returns:
        List of LBAs to write
    """
    if num_blocks <= 0:
        raise ValueError("num_blocks must be greater than 0.")
    if num_operations <= 0:
        raise ValueError("num_operations must be greater than 0.")

    rng = random.Random(seed)

    if workload_type.lower() == "uniform":
        return [rng.randint(0, num_blocks - 1) for _ in range(num_operations)]

    elif workload_type.lower() == "skewed":
        # 20% of blocks receive ~80% of updates
        num_hot = max(1, int(round(num_blocks * 0.20)))
        hot_blocks = list(range(num_hot))
        cold_blocks = list(range(num_hot, num_blocks))

        if not cold_blocks:
            cold_blocks = hot_blocks

        operations: List[int] = []
        for _ in range(num_operations):
            if rng.random() < 0.80:
                operations.append(rng.choice(hot_blocks))
            else:
                operations.append(rng.choice(cold_blocks))
        return operations

    else:
        raise ValueError(f"Unknown workload_type '{workload_type}'. Expected 'uniform' or 'skewed'.")


def populate_initial_data(
    fs: Union[InPlaceFS, LogStructuredFS],
    num_blocks: int,
    data_generator=None,
) -> None:
    """
    Populates storage with initial data up to num_blocks before measuring metrics.
    Initialization writes are excluded from WAF calculations.
    """
    # Ensure metrics measuring is OFF during initialization
    fs.metrics.stop_measuring()

    for lba in range(num_blocks):
        data = f"block_{lba}_init" if data_generator is None else data_generator(lba)
        fs.write(lba, data)
