from abc import ABCMeta
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from wake.core.visitor import Visitor

if TYPE_CHECKING:
    from wake.ir import IrAbc


class MutantStatus(Enum):
    PENDING = auto()
    KILLED = auto()
    SURVIVED = auto()
    TIMEOUT = auto()
    COMPILE_ERROR = auto()


@dataclass(frozen=True, eq=True)
class Mutation:
    """Immutable representation of a single mutation."""
    operator: str
    file_path: Path
    byte_start: int
    byte_end: int
    original: str
    replacement: str
    description: str
    node_id: Optional[int] = None
    status: MutantStatus = MutantStatus.PENDING
    
    @property
    def id(self) -> str:
        import hashlib
        data = f"{self.file_path}:{self.byte_start}:{self.original}:{self.replacement}"
        return hashlib.sha256(data.encode()).hexdigest()[:12]

    @property
    def line_number(self) -> int:
        """Convert byte offset to 1-indexed line number."""
        content = self.file_path.read_text()
        return content[:self.byte_start].count('\n') + 1

    def apply(self, source: bytes) -> bytes:
        return source[:self.byte_start] + self.replacement.encode() + source[self.byte_end:]


class Mutator(Visitor, metaclass=ABCMeta):
    """Base class for mutation operators using Wake's IR."""
    
    name: str = "base"
    description: str = "Base mutation operator"
    
    def __init__(self):
        self._mutations: List[Mutation] = []
        self._current_file: Optional[Path] = None
    
    @property
    def visit_mode(self) -> str:
        return "paths"
    
    @property
    def mutations(self) -> List[Mutation]:
        return self._mutations
    
    def _add(
        self,
        node: "IrAbc",
        original: str,
        replacement: str,
        description: Optional[str] = None,
    ) -> None:
        """Register a mutation from an IR node."""
        start, end = node.byte_location
        
        if description is None:
            description = f"{original} → {replacement}"
        
        self._mutations.append(Mutation(
            operator=self.name,
            file_path=self._current_file,
            byte_start=start,
            byte_end=end,
            original=original,
            replacement=replacement,
            description=description,
            node_id=node.ast_node_id,
        ))