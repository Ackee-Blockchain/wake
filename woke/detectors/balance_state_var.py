from __future__ import annotations

import logging
from typing import List, Optional, Set

import woke.ir as ir
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)

logger = logging.getLogger(__name__)
_recursion_guard = set()


def _process_assigned_vars(address_balance: ir.ExpressionAbc) -> List[Detection]:
    ret = []
    if address_balance in _recursion_guard:
        return ret
    _recursion_guard.add(address_balance)

    assigned_var_statement = address_balance
    parents: List[ir.IrAbc] = [address_balance]
    assigned_vars: Optional[Set[ir.AssignedVariablePath]] = None
    statement = None
    while assigned_var_statement is not None:
        if isinstance(assigned_var_statement, ir.Assignment):
            statement = assigned_var_statement
            assigned_variables = assigned_var_statement.assigned_variables
            if len(assigned_variables) > 1:
                parent = parents[-1]
                assert isinstance(parent, ir.TupleExpression)
                index = parent.components.index(parents[-2])
                assigned_vars = assigned_variables[index]
            else:
                assigned_vars = assigned_variables[0]
            break
        elif isinstance(assigned_var_statement, ir.VariableDeclarationStatement):
            statement = assigned_var_statement
            if len(assigned_var_statement.declarations) > 1:
                parent = parents[-1]
                assert isinstance(parent, ir.TupleExpression)
                index = parent.components.index(parents[-2])
                decl = assigned_var_statement.declarations[index]
                assert decl is not None
                assigned_vars = {(decl,)}
            else:
                decl = assigned_var_statement.declarations[0]
                assert decl is not None
                assigned_vars = {(decl,)}
            break
        elif isinstance(assigned_var_statement, ir.FunctionCall):
            break
        elif isinstance(assigned_var_statement, ir.FunctionCallOptions):
            break
        elif isinstance(assigned_var_statement, ir.BinaryOperation):
            if assigned_var_statement.operator in {
                ir.enums.BinaryOpOperator.EQ,
                ir.enums.BinaryOpOperator.NEQ,
            }:
                ret.append(
                    Detection(
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
            if isinstance(segment, ir.VariableDeclaration):
                if segment.is_state_variable:
                    ret.append(Detection(statement, "State variable assignment here"))

    if len(assigned_vars) > 1 or len(next(iter(assigned_vars))) > 1:
        # currently not supported
        logger.debug(f"Complex assignment not supported: {statement.source}")
        return ret

    assigned_var = next(iter(assigned_vars))[0]
    assert assigned_var != "IndexAccess" and not isinstance(assigned_var, ir.SourceUnit)
    assigned_var_statement = None
    function_def = None
    node = assigned_var
    while node is not None:
        if isinstance(node, ir.StatementAbc) and assigned_var_statement is None:
            assigned_var_statement = node
        if isinstance(node, ir.FunctionDefinition):
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
        if isinstance(ref, (ir.Identifier, ir.MemberAccess)):
            ref_statement = ref
            while ref_statement is not None:
                if isinstance(ref_statement, ir.StatementAbc):
                    break
                ref_statement = ref_statement.parent
            if ref_statement is None or ref_statement == assigned_var_statement:
                logger.debug(f"Could not find statement for {ref.source}")
                continue

            if cfg.is_reachable(assigned_var_statement, ref_statement):
                ret.extend(_process_assigned_vars(ref))
    return ret


class UnsafeAddressBalanceUseDetector(Detector):

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        print(ir.enums.GlobalSymbolsEnum.ADDRESS_BALANCE)
        return list(self._detections)

    def visit_member_access(self, node):
        if node.referenced_declaration == ir.enums.GlobalSymbolsEnum.ADDRESS_BALANCE:
            detections = _process_assigned_vars(node)
            if len(detections) > 0:
                self._detections.add(
                    DetectorResult(
                        Detection(
                            node, "Unsafe use of address.balance", tuple(detections)
                        ),
                        DetectionImpact.MEDIUM,
                        DetectionConfidence.MEDIUM,
                    ),
                )

    @detector.command("unsafe-address-balance-use")
    def unsafe_address_balance_use(self):
        """
        Address.balance is either written to a state variable or used in a strict comparison (== or !=).
        """
        pass
