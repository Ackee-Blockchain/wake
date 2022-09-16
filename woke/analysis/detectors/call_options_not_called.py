from typing import Optional

from woke.ast.enums import GlobalSymbolsEnum
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.function_call_options import FunctionCallOptions
from woke.ast.ir.expression.member_access import MemberAccess

from .api import DetectorResult, detector


@detector(FunctionCallOptions, -1002, "function-call-options-not-called")
def detect_function_call_options_not_called(
    ir_node: FunctionCallOptions,
) -> Optional[DetectorResult]:
    """
    Function with call options actually is not called, e.g. `this.externalFunction{value: targetValue}`.
    """
    if not isinstance(ir_node.parent, FunctionCall):
        return DetectorResult(ir_node, "Function call options not called")
    return None


@detector(MemberAccess, -1003, "old-gas-value-not-called")
def detect_old_gas_value_not_called(ir_node: MemberAccess) -> Optional[DetectorResult]:
    """
    Function with gas or value set actually is not called, e.g. `this.externalFunction.value(targetValue)`.
    """
    if ir_node.referenced_declaration not in {
        GlobalSymbolsEnum.FUNCTION_GAS,
        GlobalSymbolsEnum.FUNCTION_VALUE,
    }:
        return None
    parent = ir_node.parent
    assert isinstance(parent, FunctionCall)

    if not isinstance(parent.parent, FunctionCall):
        if ir_node.referenced_declaration == GlobalSymbolsEnum.FUNCTION_GAS:
            return DetectorResult(ir_node, "Function with gas not called")
        else:
            return DetectorResult(ir_node, "Function with value not called")
    return None
