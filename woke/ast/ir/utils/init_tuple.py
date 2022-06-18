from pathlib import Path
from typing import NamedTuple

from woke.compile.compilation_unit import CompilationUnit


class IrInitTuple(NamedTuple):
    file: Path
    source: bytes
    cu: CompilationUnit
