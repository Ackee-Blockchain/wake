from typing import List, Optional

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.analysis.detectors.utils import (
    expression_is_global_symbol,
    get_function_definition_from_expression,
)
from woke.ast.enums import BinaryOpOperator, GlobalSymbolsEnum
from woke.ast.ir.expression.assignment import Assignment
from woke.ast.ir.expression.binary_operation import BinaryOperation
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.index_access import IndexAccess
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.expression.tuple_expression import TupleExpression
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.expression_statement import ExpressionStatement
from woke.ast.ir.statement.if_statement import IfStatement
from woke.ast.ir.statement.variable_declaration_statement import (
    VariableDeclarationStatement,
)


def _check_variable_assigned_global_symbol(
    identifier: Identifier, symbol: GlobalSymbolsEnum
):
    ident_statement = identifier
    while ident_statement.parent and not isinstance(ident_statement, StatementAbc):
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
        if isinstance(stmt, VariableDeclarationStatement):
            for i, dec in enumerate(stmt.declarations):
                if dec is not None and dec.name == identifier.name:
                    if isinstance(stmt.initial_value, TupleExpression) and len(
                        stmt.declarations
                    ) == len(stmt.initial_value.components):
                        assigned_val = stmt.initial_value.components[i]
                    else:
                        assigned_val = stmt.initial_value
        elif (
            isinstance(stmt, ExpressionStatement)
            and isinstance(stmt.expression, Assignment)
            and isinstance(stmt.expression.left_expression, Identifier)
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


def _check_unsafe_usage(node: MemberAccess) -> Optional[DetectorResult]:
    if node.parent and node.parent.parent:
        np = node.parent
        npp = node.parent.parent
        if isinstance(np, BinaryOperation) and np.operator == BinaryOpOperator.EQ:
            if isinstance(npp, FunctionCall) or isinstance(npp, IfStatement):
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
                    tx_origin_ma, MemberAccess
                ) and expression_is_global_symbol(
                    tx_origin_ma, GlobalSymbolsEnum.TX_ORIGIN
                ):
                    if isinstance(other, MemberAccess) and expression_is_global_symbol(
                        other, GlobalSymbolsEnum.MSG_SENDER
                    ):
                        return None
                    if (
                        isinstance(other, Identifier)
                        and not other.is_ref_to_state_variable
                        and _check_variable_assigned_global_symbol(
                            other, GlobalSymbolsEnum.MSG_SENDER
                        )
                    ):
                        return None

        if isinstance(np, IndexAccess):
            if (
                isinstance(npp, BinaryOperation)
                and (npp.left_expression == np or npp.right_expression == np)
                and npp.operator == BinaryOpOperator.LT
            ):
                other_expr = (
                    npp.right_expression
                    if npp.left_expression == np
                    else npp.left_expression
                )
                if isinstance(other_expr, MemberAccess) and expression_is_global_symbol(
                    other_expr, GlobalSymbolsEnum.BLOCK_NUMBER
                ):
                    return None
            elif (
                isinstance(npp, Assignment)
                and isinstance(npp.right_expression, MemberAccess)
                and expression_is_global_symbol(
                    npp.right_expression, GlobalSymbolsEnum.BLOCK_NUMBER
                )
            ):
                return None

    return DetectorResult(node, "tx.origin used in an unsafe manner")


def detect_unsafe_tx_origin(node: MemberAccess) -> Optional[DetectorResult]:
    if expression_is_global_symbol(node, GlobalSymbolsEnum.TX_ORIGIN):
        return _check_unsafe_usage(node)


@detector(-1010, "unsafe-tx-origin")
class UnsafeTxOriginDetector(DetectorAbc):
    """
    Detects unsafe usage of tx.origin.

    Every usage of tx.origin us unsafe expect for the following:
    - tx.origin == msg.sender and it's varieties
    - timestamp[tx.origin] < block.number
    """

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_member_access(self, node: MemberAccess):
        res = detect_unsafe_tx_origin(node)
        if res:
            self._detections.add(res)
