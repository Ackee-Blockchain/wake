from typing import Optional, Tuple, Union

import wake.ir as ir
import wake.ir.types as types
from wake.core.logging import get_logger

from .utils import get_function_implementations

logger = get_logger(__name__)


def expression_is_global_symbol(
    expr: ir.ExpressionAbc, global_symbol: ir.enums.GlobalSymbol
) -> bool:
    if isinstance(expr, ir.MemberAccess):
        if expr.referenced_declaration == global_symbol:
            logger.debug(f"Expression is {global_symbol}: {expr.source}")
            return True
    elif (
        isinstance(expr, ir.FunctionCall)
        and expr.kind == ir.enums.FunctionCallKind.TYPE_CONVERSION
        and len(expr.arguments) == 1
    ):
        # payable(msg.sender) for example
        conversion = expr.expression
        if isinstance(conversion, ir.ElementaryTypeNameExpression):
            t = conversion.type
            if isinstance(t, types.Type) and isinstance(t.actual_type, types.Address):
                return expression_is_global_symbol(expr.arguments[0], global_symbol)
    elif isinstance(expr, ir.FunctionCall) and isinstance(
        expr.function_called, ir.FunctionDefinition
    ):
        func = expr.function_called
        assert isinstance(func, ir.FunctionDefinition)
        if len(func.return_parameters.parameters) == 1:
            returns = []
            if func.body is None:
                return False

            for statement in func.body.statements_iter():
                if isinstance(statement, ir.Return):
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
    expr: ir.ExpressionAbc,
) -> Tuple[Optional[ir.VariableDeclaration], ...]:
    from wake.analysis.utils import get_all_base_and_child_declarations

    if isinstance(expr, ir.Identifier):
        ref = expr.referenced_declaration
        if isinstance(ref, ir.VariableDeclaration):
            return (ref,)
    elif isinstance(expr, ir.MemberAccess):
        ref = expr.referenced_declaration
        if isinstance(ref, ir.VariableDeclaration):
            return get_variable_declarations_from_expression(expr.expression) + (ref,)
    elif isinstance(expr, ir.FunctionCall) and isinstance(
        expr.function_called, (ir.FunctionDefinition, ir.VariableDeclaration)
    ):
        func = expr.function_called

        func_expr = expr.expression
        if isinstance(func_expr, ir.Identifier):
            ret: Tuple[Optional[ir.VariableDeclaration], ...] = tuple()
        elif isinstance(func_expr, ir.MemberAccess):
            ret = get_variable_declarations_from_expression(func_expr.expression)
        else:
            return (None,)

        if isinstance(func, ir.VariableDeclaration):
            return ret + (func,)
        elif isinstance(func, ir.FunctionDefinition):
            if func.body is None:
                implementations = list(get_function_implementations(func))
                if len(implementations) == 1:
                    if isinstance(implementations[0], ir.VariableDeclaration):
                        return ret + (implementations[0],)
                    elif isinstance(implementations[0], ir.FunctionDefinition):
                        func = implementations[0]
                        assert func.body is not None
                    else:
                        return (None,)
                else:
                    return (None,)

            returns = []
            for statement in func.body.statements_iter():
                if isinstance(statement, ir.Return):
                    returns.append(statement)
            if len(returns) == 1 and returns[0].expression is not None:
                return ret + get_variable_declarations_from_expression(
                    returns[0].expression
                )

    return (None,)


def find_low_level_call_source_address(
    expression: ir.ExpressionAbc,
) -> Optional[
    Union[
        ir.ContractDefinition,
        ir.VariableDeclaration,
        ir.Literal,
        ir.enums.GlobalSymbol,
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
            if isinstance(expression.referenced_declaration, ir.enums.GlobalSymbol):
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
        (ir.ContractDefinition, ir.VariableDeclaration, ir.enums.GlobalSymbol),
    ):
        logger.debug(
            f"Unable to find source:\n{expression.source}\n{expression.parent.source}"
        )
        return None
    return referenced_declaration
