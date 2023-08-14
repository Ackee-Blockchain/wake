from __future__ import annotations

from typing import List, Optional

import woke.ir as ir
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


def _check_variable_assigned_global_symbol(
    identifier: ir.Identifier, symbol: ir.enums.GlobalSymbolsEnum
):
    from woke.analysis.utils import (
        expression_is_global_symbol,
        get_function_definition_from_expression,
    )

    ident_statement = identifier
    while ident_statement.parent and not isinstance(ident_statement, ir.StatementAbc):
        ident_statement = ident_statement.parent
    if ident_statement is None:
        return False

    fn_dec = get_function_definition_from_expression(identifier)
    if fn_dec is None or fn_dec.body is None:
        return False

    assigned_val = None
    for stmt in fn_dec.body.statements_iter():
        if stmt == ident_statement:
            break
        if isinstance(stmt, ir.VariableDeclarationStatement):
            for i, dec in enumerate(stmt.declarations):
                if dec is not None and dec.name == identifier.name:
                    if isinstance(stmt.initial_value, ir.TupleExpression) and len(
                        stmt.declarations
                    ) == len(stmt.initial_value.components):
                        assigned_val = stmt.initial_value.components[i]
                    else:
                        assigned_val = stmt.initial_value
        elif (
            isinstance(stmt, ir.ExpressionStatement)
            and isinstance(stmt.expression, ir.Assignment)
            and isinstance(stmt.expression.left_expression, ir.Identifier)
        ):
            if (
                stmt.expression.left_expression.referenced_declaration
                == identifier.referenced_declaration
            ):
                assigned_val = stmt.expression.right_expression

    if not assigned_val:
        return False

    if expression_is_global_symbol(assigned_val, symbol):
        return True
    return False


def _check_unsafe_usage(node: ir.MemberAccess) -> Optional[DetectorResult]:
    from woke.analysis.utils import expression_is_global_symbol

    if node.parent and node.parent.parent:
        np = node.parent
        npp = node.parent.parent
        if (
            isinstance(np, ir.BinaryOperation)
            and np.operator == ir.enums.BinaryOpOperator.EQ
        ):
            if isinstance(npp, ir.FunctionCall) or isinstance(npp, ir.IfStatement):
                tx_origin_ma = (
                    np.right_expression
                    if np.right_expression == node
                    else np.left_expression
                )
                other = (
                    np.left_expression
                    if np.left_expression != tx_origin_ma
                    else np.right_expression
                )
                if isinstance(
                    tx_origin_ma, ir.MemberAccess
                ) and expression_is_global_symbol(
                    tx_origin_ma, ir.enums.GlobalSymbolsEnum.TX_ORIGIN
                ):
                    if isinstance(
                        other, ir.MemberAccess
                    ) and expression_is_global_symbol(
                        other, ir.enums.GlobalSymbolsEnum.MSG_SENDER
                    ):
                        return None
                    if (
                        isinstance(other, ir.Identifier)
                        and not other.is_ref_to_state_variable
                        and _check_variable_assigned_global_symbol(
                            other, ir.enums.GlobalSymbolsEnum.MSG_SENDER
                        )
                    ):
                        return None

        if isinstance(np, ir.IndexAccess):
            if (
                isinstance(npp, ir.BinaryOperation)
                and (npp.left_expression == np or npp.right_expression == np)
                and npp.operator == ir.enums.BinaryOpOperator.LT
            ):
                other_expr = (
                    npp.right_expression
                    if npp.left_expression == np
                    else npp.left_expression
                )
                if isinstance(
                    other_expr, ir.MemberAccess
                ) and expression_is_global_symbol(
                    other_expr, ir.enums.GlobalSymbolsEnum.BLOCK_NUMBER
                ):
                    return None
            elif (
                isinstance(npp, ir.Assignment)
                and isinstance(npp.right_expression, ir.MemberAccess)
                and expression_is_global_symbol(
                    npp.right_expression, ir.enums.GlobalSymbolsEnum.BLOCK_NUMBER
                )
            ):
                return None

    return DetectorResult(
        Detection(node, "tx.origin used in an unsafe manner"),
        confidence=DetectionConfidence.LOW,
        impact=DetectionImpact.MEDIUM,
    )


def detect_unsafe_tx_origin(node: ir.MemberAccess) -> Optional[DetectorResult]:
    from woke.analysis.utils import expression_is_global_symbol

    if expression_is_global_symbol(node, ir.enums.GlobalSymbolsEnum.TX_ORIGIN):
        return _check_unsafe_usage(node)


class UnsafeTxOriginDetector(Detector):
    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_member_access(self, node: ir.MemberAccess):
        res = detect_unsafe_tx_origin(node)
        if res:
            self._detections.add(res)

    @detector.command("unsafe-tx-origin")
    def cli(self):
        """
        Detects unsafe usage of tx.origin.

        Every usage of tx.origin us unsafe expect for the following:
        - tx.origin == msg.sender and it's varieties
        - timestamp[tx.origin] < block.number
        """
        pass
