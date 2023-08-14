from __future__ import annotations

import logging
from typing import List, Set

import woke.ir as ir
import woke.ir.types as types
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)

from .reentrancy import address_is_safe, find_low_level_call_source_address

logger = logging.getLogger(__name__)


def check_delegatecall_in_function(
    function_definition: ir.FunctionDefinition,
    statement: ir.StatementAbc,
    address_source: ir.ExpressionAbc,
    checked_statements: Set[ir.StatementAbc],
) -> List[Detection]:
    from woke.analysis.ownable import statement_is_publicly_executable
    from woke.analysis.utils import pair_function_call_arguments

    if not statement_is_publicly_executable(statement):
        return []

    source_address_declaration = find_low_level_call_source_address(address_source)
    is_safe = None
    if source_address_declaration is None:
        logger.debug(f"{address_source.source}")
    elif isinstance(source_address_declaration, ir.enums.GlobalSymbolsEnum):
        if source_address_declaration == ir.enums.GlobalSymbolsEnum.THIS:
            is_safe = True
        elif source_address_declaration in {
            ir.enums.GlobalSymbolsEnum.MSG_SENDER,
            ir.enums.GlobalSymbolsEnum.TX_ORIGIN,
        }:
            is_safe = False
        else:
            is_safe = None
            logger.debug(f"{source_address_declaration}:")
    elif isinstance(source_address_declaration, ir.ContractDefinition):
        if source_address_declaration.kind == ir.enums.ContractKind.LIBRARY:
            is_safe = True
    elif isinstance(source_address_declaration, ir.Literal):
        is_safe = True
    else:
        is_safe = address_is_safe(source_address_declaration)

    if is_safe:
        return []

    checked_statements.add(statement)
    ret = []
    if function_definition.visibility in {
        ir.enums.Visibility.PUBLIC,
        ir.enums.Visibility.EXTERNAL,
    }:
        ret.append(
            Detection(
                statement,
                f"Exploitable from `{function_definition.canonical_name}`, address is safe: {is_safe}",
            )
        )

    for ref in function_definition.get_all_references(False):
        if isinstance(ref, ir.IdentifierPathPart):
            top_statement = ref.underlying_node
        elif isinstance(ref, ir.ExternalReference):
            continue  # TODO currently not supported
        else:
            top_statement = ref
        func_call = None
        while top_statement is not None:
            if (
                func_call is None
                and isinstance(top_statement, ir.FunctionCall)
                and top_statement.function_called == function_definition
            ):
                func_call = top_statement
            if isinstance(top_statement, ir.StatementAbc):
                break
            top_statement = top_statement.parent

        if top_statement is None or func_call is None:
            continue
        function_def = top_statement
        while function_def is not None and not isinstance(
            function_def, ir.FunctionDefinition
        ):
            function_def = function_def.parent
        if function_def is None:
            continue
        assert isinstance(function_def, ir.FunctionDefinition)
        if top_statement in checked_statements:
            continue

        if source_address_declaration in function_definition.parameters.parameters:
            for arg_decl, arg_expr in pair_function_call_arguments(
                function_definition, func_call
            ):
                if arg_decl == source_address_declaration:
                    assert isinstance(arg_expr.type, (types.Address, types.Contract))
                    ret.extend(
                        check_delegatecall_in_function(
                            function_def, top_statement, arg_expr, checked_statements
                        )
                    )
                    break
        else:
            ret.extend(
                check_delegatecall_in_function(
                    function_def, top_statement, address_source, checked_statements
                )
            )

    return ret


class UnsafeDelegatecallDetector(Detector):
    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_member_access(self, node: ir.MemberAccess):
        t = node.type
        if (
            not isinstance(t, types.Function)
            or t.kind
            not in {
                ir.enums.FunctionTypeKind.DELEGATE_CALL,
                ir.enums.FunctionTypeKind.BARE_DELEGATE_CALL,
            }
            or t.attached_to is not None
        ):
            return

        address_source = node.expression
        statement = node
        while statement is not None:
            if isinstance(statement, ir.StatementAbc):
                break
            statement = statement.parent
        if statement is None:
            return
        func = statement
        while func is not None:
            if isinstance(func, ir.FunctionDefinition):
                break
            func = func.parent
        if func is None:
            return

        ret = check_delegatecall_in_function(func, statement, address_source, set())
        if len(ret) == 0:
            return

        self._detections.add(
            DetectorResult(
                Detection(
                    node,
                    f"Possibly unsafe delegatecall in `{func.canonical_name}`",
                    tuple(ret),
                ),
                confidence=DetectionConfidence.MEDIUM,
                impact=DetectionImpact.HIGH,
            )
        )

    @detector.command("unsafe-delegatecall")
    def cli(self):
        """
        Delegatecall to an untrusted contract.
        """
        pass
