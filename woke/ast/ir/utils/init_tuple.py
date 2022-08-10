from pathlib import Path
from typing import Dict, NamedTuple, Optional

from intervaltree import IntervalTree

from woke.ast.ir.reference_resolver import ReferenceResolver
from woke.compile import SolcOutputContractInfo
from woke.compile.compilation_unit import CompilationUnit


class IrInitTuple(NamedTuple):
    file: Path
    source: bytes
    cu: CompilationUnit
    interval_tree: IntervalTree
    reference_resolver: ReferenceResolver
    contracts_info: Optional[Dict[str, SolcOutputContractInfo]]
