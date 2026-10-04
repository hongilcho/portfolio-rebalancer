"""Small, explicit IO dependencies shared by domain repositories."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RepositoryContext:
    # Repositories rent one connection for each existing operation. Cross-table
    # trade writes reuse that connection, rather than calling another repository.
    connect: Callable[[], Any]
    new_id: Callable[[], str]
    invalidate: Callable[[], None]
    exchange_rate: Callable[[], float] = lambda: 1380.0
