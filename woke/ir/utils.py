from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

from intervaltree import IntervalTree

if TYPE_CHECKING:
    from woke.compiler import SolcOutputContractInfo
    from woke.compiler.compilation_unit import CompilationUnit
    from woke.ir.meta.source_unit import SourceUnit
    from woke.ir.reference_resolver import ReferenceResolver


@dataclass
class IrInitTuple:
    file: Path
    source: bytes
    cu: CompilationUnit
    interval_tree: IntervalTree
    reference_resolver: ReferenceResolver
    contracts_info: Optional[Dict[str, SolcOutputContractInfo]]
    source_unit: Optional[SourceUnit] = None
