import copy
import logging
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple, Union

import networkx as nx

import woke.ast.types as types
from woke.analysis.cfg import CfgBlock
from woke.ast.enums import FunctionCallKind, GlobalSymbolsEnum
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.assignment import Assignment
from woke.ast.ir.expression.elementary_type_name_expression import (
    ElementaryTypeNameExpression,
)
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.function_call_options import FunctionCallOptions
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.statement.expression_statement import ExpressionStatement
from woke.ast.ir.statement.inline_assembly import InlineAssembly
from woke.ast.ir.statement.return_statement import Return
from woke.ast.ir.yul.abc import YulAbc
from woke.ast.ir.yul.assignment import Assignment as YulAssignment
from woke.ast.ir.yul.identifier import Identifier as YulIdentifier

logger = logging.getLogger(__name__)


def pair_function_call_arguments(
    definition: FunctionDefinition, call: FunctionCall
) -> Tuple[Tuple[VariableDeclaration, ExpressionAbc], ...]:
    if len(definition.parameters.parameters) == len(call.arguments):
        return tuple(zip(definition.parameters.parameters, call.arguments))
    elif len(definition.parameters.parameters) == len(call.arguments) + 1:
        # using for
        node = call.expression
        if isinstance(node, FunctionCallOptions):
            node = node.expression
        if isinstance(node, MemberAccess):
            node = node.expression
        return ((definition.parameters.parameters[0], node),) + tuple(
            zip(definition.parameters.parameters[1:], call.arguments)
        )
    else:
        raise ValueError(
            f"{definition.name} has {len(definition.parameters.parameters)} parameters but called with {len(call.arguments)} arguments"
        )


def get_all_base_and_child_functions(
    func: Union[FunctionDefinition, VariableDeclaration]
) -> Set[Union[FunctionDefinition, VariableDeclaration]]:
    ret = {func}
    queue: Deque[Union[FunctionDefinition, VariableDeclaration]] = deque([func])

    while len(queue) > 0:
        func = queue.popleft()

        if isinstance(func, VariableDeclaration):
            for base in func.base_functions:
                if base not in ret:
                    ret.add(base)
                    queue.append(base)
        elif isinstance(func, FunctionDefinition):
            for base in func.base_functions:
                if base not in ret:
                    ret.add(base)
                    queue.append(base)
            for child in func.child_functions:
                if child not in ret:
                    ret.add(child)
                    queue.append(child)
    return ret


def expression_is_global_symbol(
    expr: ExpressionAbc, global_symbol: GlobalSymbolsEnum
) -> bool:
    if isinstance(expr, MemberAccess):
        if expr.referenced_declaration == global_symbol:
            logger.debug(f"Expression is {global_symbol}: {expr.source}")
            return True
    elif (
        isinstance(expr, FunctionCall)
        and expr.kind == FunctionCallKind.TYPE_CONVERSION
        and len(expr.arguments) == 1
    ):
        # payable(msg.sender) for example
        conversion = expr.expression
        if isinstance(conversion, ElementaryTypeNameExpression):
            t = conversion.type
            if isinstance(t, types.Type) and isinstance(t.actual_type, types.Address):
                return expression_is_global_symbol(expr.arguments[0], global_symbol)
    elif isinstance(expr, FunctionCall) and isinstance(
        expr.function_called, FunctionDefinition
    ):
        func = expr.function_called
        assert isinstance(func, FunctionDefinition)
        if len(func.return_parameters.parameters) == 1:
            returns = []
            if func.body is None:
                return False

            for statement in func.body.statements_iter():
                if isinstance(statement, Return):
                    returns.append(statement)
            if all(
                expression_is_global_symbol(return_.expression, global_symbol)
                for return_ in returns
                if return_.expression is not None
            ):
                logger.debug(f"Expression is {global_symbol}: {expr.source}")
                return True

    logger.debug(f"Expression is NOT {global_symbol}: {expr.source}")
    return False


def get_variable_declarations_from_expression(
    expr: ExpressionAbc,
) -> Tuple[Optional[VariableDeclaration], ...]:
    if isinstance(expr, Identifier):
        ref = expr.referenced_declaration
        if isinstance(ref, VariableDeclaration):
            return (ref,)
    elif isinstance(expr, MemberAccess):
        ref = expr.referenced_declaration
        if isinstance(ref, VariableDeclaration):
            return get_variable_declarations_from_expression(expr.expression) + (ref,)
    elif isinstance(expr, FunctionCall) and isinstance(
        expr.function_called, (FunctionDefinition, VariableDeclaration)
    ):
        func = expr.function_called

        func_expr = expr.expression
        if isinstance(func_expr, Identifier):
            ret: Tuple[Optional[VariableDeclaration], ...] = tuple()
        elif isinstance(func_expr, MemberAccess):
            ret = get_variable_declarations_from_expression(func_expr.expression)
        else:
            return (None,)

        if isinstance(func, VariableDeclaration):
            return ret + (func,)
        elif isinstance(func, FunctionDefinition):
            if func.body is None:
                implementations = get_function_implementations(func)
                if len(implementations) == 1:
                    if isinstance(implementations[0], VariableDeclaration):
                        return ret + (implementations[0],)
                    elif isinstance(implementations[0], FunctionDefinition):
                        func = implementations[0]
                        assert func.body is not None
                    else:
                        return (None,)
                else:
                    return (None,)

            returns = []
            for statement in func.body.statements_iter():
                if isinstance(statement, Return):
                    returns.append(statement)
            if len(returns) == 1 and returns[0].expression is not None:
                return ret + get_variable_declarations_from_expression(
                    returns[0].expression
                )

    return (None,)


def get_function_implementations(
    function: FunctionDefinition,
) -> Tuple[Union[FunctionDefinition, VariableDeclaration], ...]:
    ret = set()
    visited: Set[Union[FunctionDefinition, VariableDeclaration]] = {function}

    queue = deque([function])
    while len(queue) > 0:
        func = queue.popleft()
        if func.implemented:
            ret.add(func)

        for f in func.child_functions:
            if f not in visited:
                visited.add(f)
                if isinstance(f, VariableDeclaration):
                    ret.add(f)
                elif isinstance(f, FunctionDefinition):
                    queue.append(f)
    return tuple(ret)


def get_function_definition_from_expression(
    expr: ExpressionAbc,
) -> Optional[FunctionDefinition]:
    fn_dec = expr
    while (
        fn_dec.parent
        and not isinstance(fn_dec, FunctionDefinition)
        and not isinstance(fn_dec, ContractDefinition)
    ):
        fn_dec = fn_dec.parent
    if (
        fn_dec is not None
        and isinstance(fn_dec, FunctionDefinition)
        and fn_dec.body is not None
    ):
        return fn_dec
    return None


def check_all_return_params_set(
    params: Tuple[VariableDeclaration],
    graph: nx.DiGraph,
    start_block: CfgBlock,
    end_block: CfgBlock,
) -> Tuple[
    bool, List[Dict[Tuple[Optional[VariableDeclaration]], Union[ExpressionAbc, YulAbc]]]
]:
    """
    Checks if all return parameters are set
    """
    out = []
    visited = set()
    all_set = _check_all_return_params_set(
        params, {}, set(), graph, start_block, end_block, out, visited
    )
    return all_set, out


def _check_all_return_params_set(
    params: Tuple[VariableDeclaration],
    solved_params: Dict[
        Tuple[Optional[VariableDeclaration]], Union[ExpressionAbc, YulAbc]
    ],
    solved_declarations: Set[VariableDeclaration],
    graph: nx.DiGraph,
    start_block: CfgBlock,
    end_block: CfgBlock,
    out: List[Dict[Tuple[Optional[VariableDeclaration]], Union[ExpressionAbc, YulAbc]]],
    visited: Set[CfgBlock],
) -> bool:
    if start_block in visited:
        return False
    visited.add(start_block)
    if len(solved_declarations) == len(params):
        out.append(solved_params)
        return True
    if start_block == end_block:
        out.append(solved_params)
        return False

    for stmt in reversed(start_block.statements):
        if isinstance(stmt, ExpressionStatement) and isinstance(
            stmt.expression, Assignment
        ):
            assigned_vars = []
            assigned_params = set()
            for vars in stmt.expression.assigned_variables:
                if vars is None:
                    continue
                for decls in vars:
                    for vd in decls:
                        if (
                            isinstance(vd, VariableDeclaration)
                            and vd in params
                            and vd not in solved_declarations
                        ):
                            assigned_vars.append(vd)
                            assigned_params.add(vd)
                        else:
                            assigned_vars.append(None)
            if len(assigned_params) > 0:
                solved_declarations.update(assigned_params)
                solved_params[tuple(assigned_vars)] = stmt.expression.right_expression
        elif isinstance(stmt, InlineAssembly) and stmt.yul_block is not None:
            for yul_stmt in stmt.yul_block.statements:
                if isinstance(yul_stmt, YulAssignment):
                    assigned_vars = []
                    assigned_params = set()
                    for var in yul_stmt.variable_names:
                        if (
                            isinstance(var, YulIdentifier)
                            and var.external_reference is not None
                            and isinstance(
                                var.external_reference.referenced_declaration,
                                VariableDeclaration,
                            )
                            and var.external_reference.referenced_declaration in params
                        ):
                            assigned_vars.append(
                                var.external_reference.referenced_declaration
                            )
                            assigned_params.add(
                                var.external_reference.referenced_declaration
                            )
                        else:
                            assigned_vars.append(None)
                    if len(assigned_params) > 0:
                        solved_declarations.update(assigned_params)
                        solved_params[tuple(assigned_vars)] = yul_stmt.value

    all_set = True
    for next_start in graph.predecessors(start_block):
        if next_start in visited:
            continue
        if not _check_all_return_params_set(
            params,
            copy.copy(solved_params),
            copy.copy(solved_declarations),
            graph,
            next_start,
            end_block,
            out,
            visited,
        ):
            all_set = False
    return all_set
