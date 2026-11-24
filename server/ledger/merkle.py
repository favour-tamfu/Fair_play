"""Merkle root of a set of chain hashes (brief §8): one 64-hex fingerprint for all plays of an hour.

Leaves = the chain hashes (hex) as bytes, SORTED (order-independent, deterministic). Each level hashes pairs with
sha256(left ‖ right); an odd node is paired with itself. One leaf → its own hash is the root. No leaves → None.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Optional


def merkle_root(chain_hashes: Iterable[str]) -> Optional[str]:
    level = sorted(bytes.fromhex(h) for h in chain_hashes)
    if not level:
        return None
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()
