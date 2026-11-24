"""Integer FCFA with largest-remainder rounding: the parts always add up to the total exactly (brief §9)."""
from __future__ import annotations

from typing import Sequence


def largest_remainder(total: int, weights: Sequence[float]) -> list[int]:
    """Split `total` (int ≥ 0) proportionally to `weights` (≥ 0) into integers summing exactly to `total`.
    Ties in the remainders go to the earlier item (deterministic). All-zero weights → all zeros."""
    s = float(sum(weights))
    if total <= 0 or s <= 0:
        return [0] * len(weights)
    raw = [total * w / s for w in weights]
    out = [int(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - out[i]), i))
    for i in order[: total - sum(out)]:
        out[i] += 1
    return out
