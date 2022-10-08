import logging
from collections import deque
from functools import reduce
from operator import or_
from typing import List, Optional, Set, Tuple, Union

import networkx as nx

import woke.ast.types as types
from woke.analysis.cfg import CfgBlock
from woke.analysis.detectors.api import DetectorResult, detector
from woke.analysis.detectors.ownable import (
    statement_is_publicly_executable,
    variable_is_owner,
)
from woke.analysis.detectors.utils import pair_function_call_arguments
from woke.ast.enums import (
    ContractKind,
    FunctionCallKind,
    FunctionTypeKind,
    GlobalSymbolsEnum,
    ModifiesStateFlag,
    Mutability,
    StateMutability,
    Visibility,
)
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.literal import Literal
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.expression.tuple_expression import TupleExpression
from woke.ast.ir.meta.identifier_path import IdentifierPathPart
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.inline_assembly import ExternalReference
from woke.ast.ir.statement.return_statement import Return
from woke.ast.ir.statement.variable_declaration_statement import (
    VariableDeclarationStatement,
)

logger = logging.getLogger(__name__)


def address_is_safe(addr: VariableDeclaration) -> Optional[bool]:
    if variable_is_owner(addr):
        return True

    if isinstance(addr.parent, ParameterList) and (
        isinstance(addr.parent.parent, FunctionDefinition)
    ):
        function_definition = addr.parent.parent
        assert isinstance(function_definition, FunctionDefinition)
        if function_definition.visibility in {Visibility.PUBLIC, Visibility.EXTERNAL}:
            return False

        return None
    elif addr.is_state_variable:
        if addr.mutability in {Mutability.CONSTANT, Mutability.IMMUTABLE}:
            return True
        return False
    elif isinstance(addr.parent, VariableDeclarationStatement):
        return None
    else:
        logger.warning(
            f"Unable to detect if address source is safe: {addr.parent}\n{addr.source}"
        )
        return None


def find_low_level_call_source_address(
    expression: ExpressionAbc,
) -> Optional[
    Union[ContractDefinition, VariableDeclaration, Literal, GlobalSymbolsEnum]
]:
    t = expression.type
    if isinstance(t, types.Type):
        if not isinstance(t.actual_type, types.Contract):
            return None
    elif not isinstance(expression.type, (types.Address, types.Contract)):
        return None

    while True:
        if isinstance(expression, (Identifier, Literal)):
            break
        elif isinstance(expression, FunctionCall):
            if expression.kind == FunctionCallKind.FUNCTION_CALL:
                function_called = expression.function_called
                if (
                    isinstance(function_called, FunctionDefinition)
                    and function_called.body is not None
                ):
                    returns = [
                        statement
                        for statement in function_called.body.statements_iter()
                        if isinstance(statement, Return)
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
            elif expression.kind == FunctionCallKind.TYPE_CONVERSION:
                if len(expression.arguments) != 1:
                    logger.debug(
                        f"Unable to find source: {expression}\n{expression.source}"
                    )
                    return None
                expression = expression.arguments[0]
        elif isinstance(expression, MemberAccess):
            if isinstance(expression.referenced_declaration, GlobalSymbolsEnum):
                return expression.referenced_declaration
            expression = expression.expression
        elif (
            isinstance(expression, TupleExpression)
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

    if isinstance(expression, Literal):
        return expression

    assert isinstance(expression, Identifier)
    referenced_declaration = expression.referenced_declaration
    if not isinstance(
        referenced_declaration,
        (ContractDefinition, VariableDeclaration, GlobalSymbolsEnum),
    ):
        logger.debug(
            f"Unable to find source:\n{expression.source}\n{expression.parent.source}"
        )
        return None
    return referenced_declaration


def _modifies_state_after_statement(
    function_definition: FunctionDefinition,
    statement: StatementAbc,
) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
    ret: Set[Tuple[IrAbc, ModifiesStateFlag]] = set()
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

    for _, to in graph.out_edges(start):
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
        for _, to in graph.out_edges(block):
            if to in visited:
                continue
            if not nx.has_path(graph, to, cfg.end_block):
                continue

            visited.add(to)
            queue.append(to)

    return ret


def check_reentrancy_in_function(
    function_definition: FunctionDefinition,
    statement: StatementAbc,
    address_source: ExpressionAbc,
    child_modifies_state: Set[Tuple[IrAbc, ModifiesStateFlag]],
    checked_statements: Set[StatementAbc],
) -> List[DetectorResult]:
    # TODO check non-reentrant
    if not statement_is_publicly_executable(statement, check_only_eoa=True):
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

    this_modifies_state = set(child_modifies_state)
    this_modifies_state.update(
        _modifies_state_after_statement(function_definition, statement)
    )

    if len(this_modifies_state) and function_definition.visibility in {
        Visibility.PUBLIC,
        Visibility.EXTERNAL,
    }:
        state_mods = reduce(or_, (mod[1] for mod in this_modifies_state))
        ret.append(
            DetectorResult(
                statement,
                f"Exploitable from `{function_definition.canonical_name}`, address is safe: {is_safe}, state modified: {str(state_mods)}",
            )
        )

    for ref in function_definition.references:
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


# @detector(VariableDeclaration, -1005, "test")
def check_reentrancy(ir_node: VariableDeclaration) -> Optional[DetectorResult]:
    if ir_node.name not in {"uniswapV2Router", "_owner"}:
        return None

    return DetectorResult(ir_node, f"Variable is owner: {variable_is_owner(ir_node)}")


@detector(MemberAccess, -1004, "reentrancy")
def detect_reentrancy(ir_node: MemberAccess) -> Optional[DetectorResult]:
    """
    Detects re-entrancy vulnerabilities.
    """

    t = ir_node.type
    if (
        not isinstance(t, types.Function)
        or t.kind
        not in {
            FunctionTypeKind.BARE_CALL,
            FunctionTypeKind.EXTERNAL,
        }
        or t.state_mutability in {StateMutability.PURE, StateMutability.VIEW}
    ):
        return None

    address_source = ir_node.expression

    function_call = ir_node
    while function_call is not None:
        if isinstance(function_call, FunctionCall):
            break
        function_call = function_call.parent
    if function_call is None:
        return None

    if function_call.function_called != ir_node.referenced_declaration:
        logger.debug(f"Re-entrancy ignored: {function_call.source}")
        return None

    statement = function_call
    while statement is not None:
        if isinstance(statement, StatementAbc):
            break
        statement = statement.parent
    if statement is None:
        return None

    function_def = statement
    while function_def is not None:
        if isinstance(function_def, FunctionDefinition):
            break
        function_def = function_def.parent
    if function_def is None:
        return None

    ret = check_reentrancy_in_function(
        function_def, statement, address_source, set(), set()
    )
    if len(ret) == 0:
        return None
    ret = list(
        sorted(ret, key=lambda x: (str(x.ir_node.file), x.ir_node.byte_location[0]))
    )

    return DetectorResult(
        ir_node, f"Possible re-entrancy in `{function_def.canonical_name}`", ret
    )
