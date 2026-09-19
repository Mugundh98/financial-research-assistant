"""Access control: role capabilities and approved-only data enforcement.

Roles form a simple capability model. `query` is open to all; forward-looking
`scenario` projections require at least analyst; only admins may `approve` a
human-in-the-loop decision. `filter_approved` enforces that only records flagged
``approved`` ever enter retrieval/computation.
"""
from __future__ import annotations

from typing import Iterable, TypeVar

from ..contracts.models import Role

CAPABILITIES: dict[str, set[Role]] = {
    "query": {Role.VIEWER, Role.ANALYST, Role.ADMIN},
    "scenario": {Role.ANALYST, Role.ADMIN},
    "approve": {Role.ADMIN},
}


def can(role: Role, capability: str) -> bool:
    return role in CAPABILITIES.get(capability, set())


def required_capability(intent: str) -> str:
    """Map a query intent to the capability it requires."""
    return "scenario" if intent == "scenario" else "query"


T = TypeVar("T")


def filter_approved(items: Iterable[T]) -> list[T]:
    """Keep only records whose ``approved`` flag is truthy."""
    return [i for i in items if getattr(i, "approved", True)]
