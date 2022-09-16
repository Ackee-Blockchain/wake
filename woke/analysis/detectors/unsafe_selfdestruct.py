import logging
from typing import Optional

from woke.analysis.detectors import DetectorResult, detector
from woke.analysis.detectors.ownable import statement_is_publicly_executable
from woke.ast.enums import GlobalSymbolsEnum
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.statement.abc import StatementAbc

logger = logging.getLogger(__name__)


@detector(FunctionCall, -100, "unsafe-selfdestruct")
def detect_unsafe_selfdestruct(ir_node: FunctionCall) -> Optional[DetectorResult]:
    """
    Selfdestruct call is not protected.
    """
    if ir_node.function_called not in {
        GlobalSymbolsEnum.SELFDESTRUCT,
        GlobalSymbolsEnum.SUICIDE,
    }:
        return None

    node = ir_node
    while node is not None:
        if isinstance(node, StatementAbc):
            break
        node = node.parent
    if node is None:
        return None
    if not statement_is_publicly_executable(node):
        return None

    return DetectorResult(ir_node, "Selfdestruct call is not protected")
