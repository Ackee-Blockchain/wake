import logging
from collections import deque
from functools import lru_cache
from typing import Optional, Set, Tuple

import woke.ast.types as types
from woke.analysis.cfg import CfgBlock, TransitionCondition
from woke.analysis.detectors.utils import (
    expression_is_global_symbol,
    get_variable_declaration_from_expression,
    pair_function_call_arguments,
)
from woke.ast.enums import (
    BinaryOpOperator,
    FunctionKind,
    GlobalSymbolsEnum,
    Mutability,
    Visibility,
)
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.assignment import Assignment
from woke.ast.ir.expression.binary_operation import BinaryOperation
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.index_access import IndexAccess
from woke.ast.ir.expression.tuple_expression import TupleExpression
from woke.ast.ir.meta.identifier_path import IdentifierPathPart
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.expression_statement import ExpressionStatement
from woke.ast.ir.statement.inline_assembly import ExternalReference
from woke.ast.ir.statement.placeholder_statement import PlaceholderStatement
from woke.ast.ir.statement.return_statement import Return
from woke.utils import recursion_guard, return_on_recursion

logger = logging.getLogger(__name__)


def expression_is_only_owner(
    expression: ExpressionAbc,
    msg_sender_variables: Set[VariableDeclaration],
    check_only_eoa: bool = False,
    inverted: bool = False,
) -> bool:
    if isinstance(expression, BinaryOperation):
        if expression.operator in {BinaryOpOperator.EQ, BinaryOpOperator.NEQ}:
            left = get_variable_declaration_from_expression(expression.left_expression)
            right = get_variable_declaration_from_expression(
                expression.right_expression
            )

            left_is_msg_sender = (
                left is not None and left in msg_sender_variables
            ) or expression_is_global_symbol(
                expression.left_expression, GlobalSymbolsEnum.MSG_SENDER
            )
            right_is_msg_sender = (
                right is not None and right in msg_sender_variables
            ) or expression_is_global_symbol(
                expression.right_expression, GlobalSymbolsEnum.MSG_SENDER
            )
            left_is_owner = left is not None and variable_is_owner(left)
            right_is_owner = right is not None and variable_is_owner(right)

            if check_only_eoa:
                if left_is_msg_sender and expression_is_global_symbol(
                    expression.right_expression, GlobalSymbolsEnum.TX_ORIGIN
                ):
                    return True
                if right_is_msg_sender and expression_is_global_symbol(
                    expression.left_expression, GlobalSymbolsEnum.TX_ORIGIN
                ):
                    return True

            if (left_is_msg_sender and right_is_owner) or (
                right_is_msg_sender and left_is_owner
            ):
                if (not inverted and expression.operator == BinaryOpOperator.EQ) or (
                    inverted and expression.operator == BinaryOpOperator.NEQ
                ):
                    return True
        elif expression.operator == BinaryOpOperator.BOOLEAN_OR:
            if not inverted:
                return expression_is_only_owner(
                    expression.left_expression,
                    msg_sender_variables,
                    check_only_eoa=check_only_eoa,
                ) and expression_is_only_owner(
                    expression.right_expression,
                    msg_sender_variables,
                    check_only_eoa=check_only_eoa,
                )
            else:
                return expression_is_only_owner(
                    expression.left_expression,
                    msg_sender_variables,
                    check_only_eoa=check_only_eoa,
                    inverted=False,
                ) or expression_is_only_owner(
                    expression.right_expression,
                    msg_sender_variables,
                    check_only_eoa=check_only_eoa,
                    inverted=False,
                )
        elif expression.operator == BinaryOpOperator.BOOLEAN_AND:
            if not inverted:
                return expression_is_only_owner(
                    expression.left_expression,
                    msg_sender_variables,
                    check_only_eoa=check_only_eoa,
                ) or expression_is_only_owner(
                    expression.right_expression,
                    msg_sender_variables,
                    check_only_eoa=check_only_eoa,
                )
            else:
                return expression_is_only_owner(
                    expression.left_expression,
                    msg_sender_variables,
                    check_only_eoa=check_only_eoa,
                    inverted=False,
                ) and expression_is_only_owner(
                    expression.right_expression,
                    msg_sender_variables,
                    check_only_eoa=check_only_eoa,
                    inverted=False,
                )
    elif isinstance(expression, FunctionCall) and isinstance(
        expression.type, types.Bool
    ):
        func = expression.function_called
        if isinstance(func, FunctionDefinition):
            if func.body is None:
                return False

            sender_variables = set(msg_sender_variables)

            logger.debug(f"{expression.source} is a function call to {func.source}")
            for arg_decl, arg_expr in pair_function_call_arguments(func, expression):
                if expression_is_global_symbol(arg_expr, GlobalSymbolsEnum.MSG_SENDER):
                    sender_variables.add(arg_decl)

            returns = []
            for statement in func.body.statements_iter():
                if isinstance(statement, Return):
                    returns.append(statement)
            if len(returns) > 0 and all(
                expression_is_only_owner(
                    return_.expression,
                    sender_variables,
                    check_only_eoa=check_only_eoa,
                    inverted=inverted,
                )
                for return_ in returns
                if return_.expression is not None
            ):
                logger.debug(f"Expression is only owner: {expression.source}")
                return True
    elif (
        isinstance(expression, IndexAccess)
        and expression.index_expression is not None
        and not inverted
    ):
        possible_owners = get_variable_declaration_from_expression(
            expression.base_expression
        )
        if (
            possible_owners is not None
            and variable_is_owner(possible_owners)
            and expression_is_global_symbol(
                expression.index_expression, GlobalSymbolsEnum.MSG_SENDER
            )
        ):
            logger.debug(f"Expression is only owner: {expression.source}")
            return True
    elif (
        isinstance(expression, TupleExpression)
        and len(expression.components) == 1
        and expression.components[0] is not None
    ):
        return expression_is_only_owner(
            expression.components[0],
            msg_sender_variables,
            check_only_eoa=check_only_eoa,
            inverted=inverted,
        )

    logger.debug(f"Expression is NOT only owner: {expression.source}")
    return False


_publicly_callable_recursion_guard = set()


def statement_is_only_owner(statement: StatementAbc, check_only_eoa: bool) -> bool:
    if not isinstance(statement, ExpressionStatement):
        return False
    expr = statement.expression
    if isinstance(expr, FunctionCall):
        function_called = expr.function_called
        if function_called == GlobalSymbolsEnum.REQUIRE:
            return expression_is_only_owner(
                expr.arguments[0], set(), check_only_eoa=check_only_eoa
            )
        elif (
            isinstance(function_called, FunctionDefinition)
            and function_called.body is not None
        ):
            cfg = function_called.cfg
            assert cfg is not None
            if len(cfg.end_block.statements) > 0:
                return statement_is_publicly_executable(
                    cfg.end_block.statements[-1], False, check_only_eoa=check_only_eoa
                )
    return False


_statement_is_publicly_executable_recursion_guard = set()


@lru_cache(maxsize=2048)
def statement_is_publicly_executable(
    statement: StatementAbc,
    check_func_visibility: bool = True,
    check_only_eoa: bool = False,
) -> bool:
    if (
        statement,
        check_func_visibility,
        check_only_eoa,
    ) in _statement_is_publicly_executable_recursion_guard:
        return False

    with recursion_guard(
        _statement_is_publicly_executable_recursion_guard,
        statement,
        check_func_visibility,
        check_only_eoa,
    ):
        decl = statement
        while decl is not None:
            if isinstance(decl, (FunctionDefinition, ModifierDefinition)):
                break
            decl = decl.parent
        assert isinstance(decl, (FunctionDefinition, ModifierDefinition))

        if isinstance(decl, FunctionDefinition):
            if decl.kind == FunctionKind.CONSTRUCTOR:
                return False
            for modifier in decl.modifiers:
                mod = modifier.modifier_name.referenced_declaration
                assert isinstance(mod, ModifierDefinition)
                if mod.body is None:
                    continue
                placeholders = [
                    s
                    for s in mod.body.statements_iter()
                    if isinstance(s, PlaceholderStatement)
                ]
                if not any(
                    statement_is_publicly_executable(s, check_only_eoa=check_only_eoa)
                    for s in placeholders
                ):
                    return False

        cfg = decl.cfg
        assert cfg is not None

        block = cfg.get_cfg_block(statement)
        if statement not in block.statements:
            assert statement == block.control_statement
            if any(
                statement_is_only_owner(s, check_only_eoa) for s in block.statements
            ):
                return False
        else:
            index = block.statements.index(statement)
            if any(
                statement_is_only_owner(s, check_only_eoa)
                for s in block.statements[:index]
            ):
                return False

        if block == cfg.start_block:
            reached_start = True
        else:
            graph = cfg.graph
            visited = {block}
            queue = deque([block])
            reached_start = False

            while len(queue) > 0:
                block = queue.popleft()
                from_: CfgBlock
                condition: Tuple[TransitionCondition, Optional[ExpressionAbc]]
                for from_, _, data in graph.in_edges(block, data=True):
                    if from_ in visited:
                        continue
                    condition = data["condition"]
                    if (
                        (condition[0] == TransitionCondition.NEVER)
                        or (
                            condition[0] == TransitionCondition.IS_TRUE
                            and condition[1] is not None
                            and expression_is_only_owner(
                                condition[1], set(), check_only_eoa=check_only_eoa
                            )
                        )
                        or (
                            condition[0] == TransitionCondition.IS_FALSE
                            and condition[1] is not None
                            and expression_is_only_owner(
                                condition[1],
                                set(),
                                check_only_eoa=check_only_eoa,
                                inverted=True,
                            )
                        )
                    ):
                        continue

                    if any(
                        statement_is_only_owner(s, check_only_eoa)
                        for s in from_.statements
                    ):
                        continue

                    if from_ == cfg.start_block:
                        reached_start = True
                        break

                    visited.add(from_)
                    queue.append(from_)

        if not reached_start:
            return False
        if isinstance(decl, ModifierDefinition) or not check_func_visibility:
            return True
        if decl.visibility in {Visibility.PUBLIC, Visibility.EXTERNAL}:
            return True

        for ref in decl.references:
            if isinstance(ref, IdentifierPathPart):
                calling_statement = ref.underlying_node
            elif isinstance(ref, ExternalReference):
                continue  # TODO currently not supported
            else:
                calling_statement = ref
            while calling_statement is not None:
                if isinstance(calling_statement, StatementAbc):
                    break
                calling_statement = calling_statement.parent
            if calling_statement is not None and statement_is_publicly_executable(
                calling_statement, check_only_eoa=check_only_eoa
            ):
                return True
        return False


@return_on_recursion(True)
def variable_is_owner(variable: VariableDeclaration) -> bool:
    is_mapping_owners = (
        isinstance(variable.type, types.Mapping)
        and isinstance(variable.type.key_type, types.Address)
        and isinstance(variable.type.value_type, types.Bool)
    )

    if (
        not isinstance(variable.type, (types.Address, types.Contract))
        and not is_mapping_owners
    ):
        return False
    if variable.mutability in {Mutability.CONSTANT, Mutability.IMMUTABLE}:
        return True
    if not variable.is_state_variable:
        return False

    for ref in variable.references:
        # ref is assignment?
        if isinstance(ref, IdentifierPathPart):
            node = ref.underlying_node
        elif isinstance(ref, ExternalReference):
            continue  # TODO currently not supported
        else:
            node = ref
        is_assignment = False
        while node is not None:
            if isinstance(node, Assignment):
                for assigned_paths in node.assigned_variables:
                    if assigned_paths is not None:
                        for assigned_path in assigned_paths:
                            if variable in assigned_path:
                                is_assignment = True
                break
            node = node.parent

        if not is_assignment:
            continue

        if isinstance(ref, IdentifierPathPart):
            node = ref.underlying_node
        elif isinstance(ref, ExternalReference):
            continue  # TODO currently not supported
        else:
            node = ref
        while node is not None:
            if isinstance(node, StatementAbc):
                break
            node = node.parent
        if node is not None and statement_is_publicly_executable(node):
            logger.debug(f"Variable is NOT owner: {variable.source} {node.source}")
            return False

    return True
