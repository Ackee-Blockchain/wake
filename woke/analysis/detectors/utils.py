import logging
from collections import deque
from typing import Optional, Set, Tuple, Union

import woke.ast.types as types
from woke.ast.enums import FunctionCallKind, GlobalSymbolsEnum
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.elementary_type_name_expression import (
    ElementaryTypeNameExpression,
)
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.function_call_options import FunctionCallOptions
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.statement.return_statement import Return

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
            ret: Tuple[Optional[VariableDeclaration]] = tuple()
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
