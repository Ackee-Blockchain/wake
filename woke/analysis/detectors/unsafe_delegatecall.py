import logging
from typing import List, Set

import woke.ast.types as types
from woke.analysis.detectors.api import DetectorAbc, DetectorResult, detector
from woke.analysis.detectors.ownable import statement_is_publicly_executable
from woke.analysis.detectors.reentrancy import (
    address_is_safe,
    find_low_level_call_source_address,
)
from woke.analysis.detectors.utils import pair_function_call_arguments
from woke.ast.enums import ContractKind, FunctionTypeKind, GlobalSymbolsEnum, Visibility
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.literal import Literal
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.meta.identifier_path import IdentifierPathPart
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.inline_assembly import ExternalReference

logger = logging.getLogger(__name__)


def check_delegatecall_in_function(
    function_definition: FunctionDefinition,
    statement: StatementAbc,
    address_source: ExpressionAbc,
    checked_statements: Set[StatementAbc],
) -> List[DetectorResult]:
    if not statement_is_publicly_executable(statement):
        return []

    source_address_declaration = find_low_level_call_source_address(address_source)
    is_safe = None
    if source_address_declaration is None:
        logger.debug(f"{address_source.source}")
    elif isinstance(source_address_declaration, GlobalSymbolsEnum):
        if source_address_declaration == GlobalSymbolsEnum.THIS:
            is_safe = True
        elif source_address_declaration in {
            GlobalSymbolsEnum.MSG_SENDER,
            GlobalSymbolsEnum.TX_ORIGIN,
        }:
            is_safe = False
        else:
            is_safe = None
            logger.debug(f"{source_address_declaration}:")
    elif isinstance(source_address_declaration, ContractDefinition):
        if source_address_declaration.kind == ContractKind.LIBRARY:
            is_safe = True
    elif isinstance(source_address_declaration, Literal):
        is_safe = True
    else:
        is_safe = address_is_safe(source_address_declaration)

    if is_safe:
        return []

    checked_statements.add(statement)
    ret = []
    if function_definition.visibility in {Visibility.PUBLIC, Visibility.EXTERNAL}:
        ret.append(
            DetectorResult(
                statement,
                f"Exploitable from `{function_definition.canonical_name}`, address is safe: {is_safe}",
            )
        )

    for ref in function_definition.get_all_references(False):
        if isinstance(ref, IdentifierPathPart):
            top_statement = ref.underlying_node
        elif isinstance(ref, ExternalReference):
            continue  # TODO currently not supported
        else:
            top_statement = ref
        func_call = None
        while top_statement is not None:
            if (
                func_call is None
                and isinstance(top_statement, FunctionCall)
                and top_statement.function_called == function_definition
            ):
                func_call = top_statement
            if isinstance(top_statement, StatementAbc):
                break
            top_statement = top_statement.parent

        if top_statement is None or func_call is None:
            continue
        function_def = top_statement
        while function_def is not None and not isinstance(
            function_def, FunctionDefinition
        ):
            function_def = function_def.parent
        if function_def is None:
            continue
        assert isinstance(function_def, FunctionDefinition)
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


@detector(-1005, "unsafe-delegatecall")
class UnsafeDelegatecallDetector(DetectorAbc):
    """
    Delegatecall to an untrusted contract.
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_member_access(self, node: MemberAccess):
        t = node.type
        if (
            not isinstance(t, types.Function)
            or t.kind
            not in {
                FunctionTypeKind.DELEGATE_CALL,
                FunctionTypeKind.BARE_DELEGATE_CALL,
            }
            or t.attached_to is not None
        ):
            return

        address_source = node.expression
        statement = node
        while statement is not None:
            if isinstance(statement, StatementAbc):
                break
            statement = statement.parent
        if statement is None:
            return
        func = statement
        while func is not None:
            if isinstance(func, FunctionDefinition):
                break
            func = func.parent
        if func is None:
            return

        ret = check_delegatecall_in_function(func, statement, address_source, set())
        if len(ret) == 0:
            return

        self._detections.add(
            DetectorResult(
                node,
                f"Possibly unsafe delegatecall in `{func.canonical_name}`",
                tuple(ret),
            )
        )
