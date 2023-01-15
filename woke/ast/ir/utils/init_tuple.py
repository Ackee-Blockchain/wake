from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict, NamedTuple, Optional

from intervaltree import IntervalTree

if TYPE_CHECKING:
    from woke.ast.ir.reference_resolver import ReferenceResolver
    from woke.compiler import SolcOutputContractInfo
    from woke.compiler.compilation_unit import CompilationUnit


class IrInitTuple(NamedTuple):
    file: Path
    source: bytes
    cu: CompilationUnit
    interval_tree: IntervalTree
    reference_resolver: ReferenceResolver
    contracts_info: Optional[Dict[str, SolcOutputContractInfo]]
