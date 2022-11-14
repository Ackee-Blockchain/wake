import logging
from typing import List, Optional, Set

from woke.analysis.detectors.api import DetectorAbc, DetectorResult, detector
from woke.ast.enums import BinaryOpOperator, GlobalSymbolsEnum
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.assignment import AssignedVariablePath, Assignment
from woke.ast.ir.expression.binary_operation import BinaryOperation
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.function_call_options import FunctionCallOptions
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.expression.tuple_expression import TupleExpression
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.variable_declaration_statement import (
    VariableDeclarationStatement,
)

logger = logging.getLogger(__name__)
_recursion_guard = set()


def _process_assigned_vars(address_balance: ExpressionAbc) -> List[DetectorResult]:
    ret = []
    if address_balance in _recursion_guard:
        return ret
    _recursion_guard.add(address_balance)

    assigned_var_statement = address_balance
    parents: List[IrAbc] = [address_balance]
    assigned_vars: Optional[Set[AssignedVariablePath]] = None
    statement = None
    while assigned_var_statement is not None:
        if isinstance(assigned_var_statement, Assignment):
            statement = assigned_var_statement
            assigned_variables = assigned_var_statement.assigned_variables
            if len(assigned_variables) > 1:
                parent = parents[-1]
                assert isinstance(parent, TupleExpression)
                index = parent.components.index(parents[-2])
                assigned_vars = assigned_variables[index]
            else:
                assigned_vars = assigned_variables[0]
            break
        elif isinstance(assigned_var_statement, VariableDeclarationStatement):
            statement = assigned_var_statement
            if len(assigned_var_statement.declarations) > 1:
                parent = parents[-1]
                assert isinstance(parent, TupleExpression)
                index = parent.components.index(parents[-2])
                decl = assigned_var_statement.declarations[index]
                assert decl is not None
                assigned_vars = {(decl,)}
            else:
                decl = assigned_var_statement.declarations[0]
                assert decl is not None
                assigned_vars = {(decl,)}
            break
        elif isinstance(assigned_var_statement, FunctionCall):
            break
        elif isinstance(assigned_var_statement, FunctionCallOptions):
            break
        elif isinstance(assigned_var_statement, BinaryOperation):
            if assigned_var_statement.operator in {
                BinaryOpOperator.EQ,
                BinaryOpOperator.NEQ,
            }:
                ret.append(
                    DetectorResult(
                        assigned_var_statement,
                        f"Strict comparison on expression originating from address.balance",
                    )
                )

        parents.append(assigned_var_statement)
        assigned_var_statement = assigned_var_statement.parent

    if assigned_vars is None:
        return ret

    assert statement is not None
    for var in assigned_vars:
        for segment in var:
            if isinstance(segment, VariableDeclaration):
                if segment.is_state_variable:
                    ret.append(
                        DetectorResult(statement, "State variable assignment here")
                    )

    if len(assigned_vars) > 1 or len(next(iter(assigned_vars))) > 1:
        # currently not supported
        logger.debug(f"Complex assignment not supported: {statement.source}")
        return ret

    assigned_var = next(iter(assigned_vars))[0]
    assert assigned_var != "IndexAccess"
    assigned_var_statement = None
    function_def = None
    node = assigned_var
    while node is not None:
        if isinstance(node, StatementAbc) and assigned_var_statement is None:
            assigned_var_statement = node
        if isinstance(node, FunctionDefinition):
            function_def = node
            break
        node = node.parent
    if assigned_var_statement is None:
        logger.debug(f"Could not find statement for {assigned_var.source}")
        return ret
    if function_def is None:
        logger.debug(f"Could not find function definition for {assigned_var.source}")
        return ret

    cfg = function_def.cfg
    assert cfg is not None

    for ref in assigned_var.references:
        if isinstance(ref, (Identifier, MemberAccess)):
            ref_statement = ref
            while ref_statement is not None:
                if isinstance(ref_statement, StatementAbc):
                    break
                ref_statement = ref_statement.parent
            if ref_statement is None or ref_statement == assigned_var_statement:
                logger.debug(f"Could not find statement for {ref.source}")
                continue

            if cfg.is_reachable(assigned_var_statement, ref_statement):
                ret.extend(_process_assigned_vars(ref))
    return ret


@detector(-1003, "unsafe-address-balance-use")
class UnsafeAddressBalanceUseDetector(DetectorAbc):
    """
    Address.balance is either written to a state variable or used in a strict comparison (== or !=).
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_member_access(self, node: MemberAccess):
        if node.referenced_declaration == GlobalSymbolsEnum.ADDRESS_BALANCE:
            detections = _process_assigned_vars(node)
            if len(detections) > 0:
                self._detections.add(
                    DetectorResult(
                        node, "Unsafe use of address.balance", tuple(detections)
                    )
                )
