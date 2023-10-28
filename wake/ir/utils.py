from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

from intervaltree import IntervalTree

if TYPE_CHECKING:
    from wake.compiler import SolcOutputContractInfo
    from wake.compiler.compilation_unit import CompilationUnit
    from wake.ir.meta.source_unit import SourceUnit
    from wake.ir.reference_resolver import ReferenceResolver
    from wake.ir.statements.inline_assembly import InlineAssembly


@dataclass
class IrInitTuple:
    file: Path
    source: bytes
    cu: CompilationUnit
    interval_tree: IntervalTree
    reference_resolver: ReferenceResolver
    contracts_info: Optional[Dict[str, SolcOutputContractInfo]]
    source_unit: Optional[SourceUnit] = None
    inline_assembly: Optional[InlineAssembly] = None
