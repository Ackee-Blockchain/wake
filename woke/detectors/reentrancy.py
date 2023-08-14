from __future__ import annotations

import logging
from collections import deque
from functools import reduce
from operator import or_
from typing import List, Optional, Set, Tuple, Union

import networkx as nx

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

logger = logging.getLogger(__name__)


def address_is_safe(addr: ir.VariableDeclaration) -> Optional[bool]:
    from woke.analysis.ownable import variable_is_owner

    if variable_is_owner(addr):
        return True

    if isinstance(addr.parent, ir.ParameterList) and (
        isinstance(addr.parent.parent, ir.FunctionDefinition)
    ):
        function_definition = addr.parent.parent
        assert isinstance(function_definition, ir.FunctionDefinition)
        if function_definition.visibility in {
            ir.enums.Visibility.PUBLIC,
            ir.enums.Visibility.EXTERNAL,
        }:
            return False

        return None
    elif addr.is_state_variable:
        if addr.mutability in {
            ir.enums.Mutability.CONSTANT,
            ir.enums.Mutability.IMMUTABLE,
        }:
            return True
        return False
    elif isinstance(addr.parent, ir.VariableDeclarationStatement):
        return None
    else:
        logger.warning(
            f"Unable to detect if address source is safe: {addr.parent}\n{addr.source}"
        )
        return None


def find_low_level_call_source_address(
    expression: ir.ExpressionAbc,
) -> Optional[
    Union[
        ir.ContractDefinition,
        ir.VariableDeclaration,
        ir.Literal,
        ir.enums.GlobalSymbolsEnum,
    ]
]:
    t = expression.type
    if isinstance(t, types.Type):
        if not isinstance(t.actual_type, types.Contract):
            return None
    elif not isinstance(expression.type, (types.Address, types.Contract)):
        return None

    while True:
        if isinstance(expression, (ir.Identifier, ir.Literal)):
            break
        elif isinstance(expression, ir.FunctionCall):
            if expression.kind == ir.enums.FunctionCallKind.FUNCTION_CALL:
                function_called = expression.function_called
                if (
                    isinstance(function_called, ir.FunctionDefinition)
                    and function_called.body is not None
                ):
                    returns = [
                        statement
                        for statement in function_called.body.statements_iter()
                        if isinstance(statement, ir.Return)
                    ]

                    if len(returns) == 1 and returns[0].expression is not None:
                        expression = returns[0].expression
                    else:
                        return None
                else:
                    logger.debug(
                        f"Unable to find source: {expression.expression}\n{expression.source}"
                    )
                    return None
            elif expression.kind == ir.enums.FunctionCallKind.TYPE_CONVERSION:
                if len(expression.arguments) != 1:
                    logger.debug(
                        f"Unable to find source: {expression}\n{expression.source}"
                    )
                    return None
                expression = expression.arguments[0]
        elif isinstance(expression, ir.MemberAccess):
            if isinstance(
                expression.referenced_declaration, ir.enums.GlobalSymbolsEnum
            ):
                return expression.referenced_declaration
            expression = expression.expression
        elif (
            isinstance(expression, ir.TupleExpression)
            and len(expression.components) == 1
            and expression.components[0] is not None
        ):
            expression = expression.components[0]
        else:
            logger.debug(f"Unable to find source: {expression}\n{expression.source}")
            return None

    t = expression.type
    if isinstance(t, types.Type):
        if not isinstance(t.actual_type, types.Contract):
            return None
    elif not isinstance(expression.type, (types.Address, types.Contract)):
        logger.debug(f"Unable to find source: {expression.source}")
        return None

    if isinstance(expression, ir.Literal):
        return expression

    assert isinstance(expression, ir.Identifier)
    referenced_declaration = expression.referenced_declaration
    if not isinstance(
        referenced_declaration,
        (ir.ContractDefinition, ir.VariableDeclaration, ir.enums.GlobalSymbolsEnum),
    ):
        logger.debug(
            f"Unable to find source:\n{expression.source}\n{expression.parent.source}"
        )
        return None
    return referenced_declaration


def _modifies_state_after_statement(
    function_definition: ir.FunctionDefinition,
    statement: ir.StatementAbc,
) -> Set[Tuple[ir.IrAbc, ir.enums.ModifiesStateFlag]]:
    from woke.analysis.cfg import CfgBlock

    ret: Set[Tuple[ir.IrAbc, ir.enums.ModifiesStateFlag]] = set()
    cfg = function_definition.cfg
    assert cfg is not None
    start = cfg.get_cfg_block(statement)
    graph = cfg.graph

    if not nx.has_path(graph, start, cfg.end_block):
        return ret

    if statement not in start.statements:
        assert statement == start.control_statement
    else:
        index = start.statements.index(statement)
        for s in start.statements[index + 1 :]:
            ret.update(s.modifies_state)
        if start.control_statement is not None:
            ret.update(start.control_statement.modifies_state)

    queue = deque([])
    visited: Set[CfgBlock] = set()

    for _, to in graph.out_edges(start):  # pyright: ignore reportGeneralTypeIssues
        if to in visited:
            continue
        if not nx.has_path(graph, to, cfg.end_block):
            continue
        queue.append(to)

    while len(queue):
        block = queue.popleft()
        for s in block.statements:
            ret.update(s.modifies_state)
        if block.control_statement is not None:
            ret.update(block.control_statement.modifies_state)

        to: CfgBlock
        for _, to in graph.out_edges(block):  # pyright: ignore reportGeneralTypeIssues
            if to in visited:
                continue
            if not nx.has_path(graph, to, cfg.end_block):
                continue

            visited.add(to)
            queue.append(to)

    return ret


def check_reentrancy_in_function(
    function_definition: ir.FunctionDefinition,
    statement: ir.StatementAbc,
    address_source: ir.ExpressionAbc,
    child_modifies_state: Set[Tuple[ir.IrAbc, ir.enums.ModifiesStateFlag]],
    checked_statements: Set[ir.StatementAbc],
) -> List[Detection]:
    from woke.analysis.ownable import statement_is_publicly_executable
    from woke.analysis.utils import (
        get_all_base_and_child_functions,
        pair_function_call_arguments,
    )

    # TODO check non-reentrant
    if not statement_is_publicly_executable(statement, check_only_eoa=True):
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

    this_modifies_state = set(child_modifies_state)
    this_modifies_state.update(
        _modifies_state_after_statement(function_definition, statement)
    )

    if len(this_modifies_state) and function_definition.visibility in {
        ir.enums.Visibility.PUBLIC,
        ir.enums.Visibility.EXTERNAL,
    }:
        state_mods = reduce(or_, (mod[1] for mod in this_modifies_state))
        ret.append(
            Detection(
                statement,
                f"Exploitable from `{function_definition.canonical_name}`, address is safe: {is_safe}, state modified: {str(state_mods)}",
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
                and top_statement.function_called
                in get_all_base_and_child_functions(function_definition)
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
                        check_reentrancy_in_function(
                            function_def,
                            top_statement,
                            arg_expr,
                            this_modifies_state,
                            checked_statements,
                        )
                    )
                    break
        else:
            ret.extend(
                check_reentrancy_in_function(
                    function_def,
                    top_statement,
                    address_source,
                    this_modifies_state,
                    checked_statements,
                )
            )
    return ret


class ReentrancyDetector(Detector):
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
                ir.enums.FunctionTypeKind.BARE_CALL,
                ir.enums.FunctionTypeKind.EXTERNAL,
            }
            or t.state_mutability
            in {ir.enums.StateMutability.PURE, ir.enums.StateMutability.VIEW}
        ):
            return

        address_source = node.expression

        function_call = node
        while function_call is not None:
            if isinstance(function_call, ir.FunctionCall):
                break
            function_call = function_call.parent
        if function_call is None:
            return

        if function_call.function_called != node.referenced_declaration:
            logger.debug(f"Re-entrancy ignored: {function_call.source}")
            return

        statement = function_call
        while statement is not None:
            if isinstance(statement, ir.StatementAbc):
                break
            statement = statement.parent
        if statement is None:
            return

        function_def = statement
        while function_def is not None:
            if isinstance(function_def, ir.FunctionDefinition):
                break
            function_def = function_def.parent
        if function_def is None:
            return

        ret = check_reentrancy_in_function(
            function_def, statement, address_source, set(), set()
        )
        if len(ret) == 0:
            return
        ret = list(
            sorted(ret, key=lambda x: (str(x.ir_node.file), x.ir_node.byte_location[0]))
        )

        self._detections.add(
            DetectorResult(
                Detection(
                    node,
                    f"Possible re-entrancy in `{function_def.canonical_name}`",
                    tuple(ret),
                ),
                impact=DetectionImpact.MEDIUM,
                confidence=DetectionConfidence.MEDIUM,
            )
        )

    @detector.command("reentrancy")
    def cli(self):
        """
        Detects re-entrancy vulnerabilities.
        """
        pass
