import logging
from collections import deque
from typing import Optional, Set, Tuple, Union

import wake.ir.types as types
from wake.analysis.cfg import CfgNode, ControlFlowGraph, TransitionConditionKind
from wake.analysis.utils import pair_function_call_arguments
from wake.core import get_logger
from wake.ir import (
    Assignment,
    BinaryOperation,
    ExpressionAbc,
    ExpressionStatement,
    ExternalReference,
    FunctionCall,
    FunctionDefinition,
    IdentifierPathPart,
    IndexAccess,
    ModifierDefinition,
    ParameterList,
    PlaceholderStatement,
    Return,
    StatementAbc,
    TupleExpression,
    VariableDeclaration,
    VariableDeclarationStatement,
    YulFunctionDefinition,
    YulStatementAbc,
)
from wake.ir.enums import (
    BinaryOpOperator,
    FunctionKind,
    GlobalSymbol,
    Mutability,
    Visibility,
)
from wake.utils import cached_return_on_recursion, return_on_recursion

from .expressions import (
    expression_is_global_symbol,
    get_variable_declarations_from_expression,
)

logger = get_logger(__name__)


def expression_is_only_owner(
    expression: ExpressionAbc,
    msg_sender_variables: Set[VariableDeclaration],
    check_only_eoa: bool = False,
    inverted: bool = False,
) -> bool:
    if isinstance(expression, BinaryOperation):
        if expression.operator in {BinaryOpOperator.EQ, BinaryOpOperator.NEQ}:
            left = get_variable_declarations_from_expression(expression.left_expression)
            right = get_variable_declarations_from_expression(
                expression.right_expression
            )

            left_is_msg_sender = (
                len(left) == 1 and left[0] in msg_sender_variables
            ) or expression_is_global_symbol(
                expression.left_expression, GlobalSymbol.MSG_SENDER
            )
            right_is_msg_sender = (
                len(right) == 1 and right[0] in msg_sender_variables
            ) or expression_is_global_symbol(
                expression.right_expression, GlobalSymbol.MSG_SENDER
            )
            left_is_owner = not any(var is None for var in left) and all(variable_is_owner(var) for var in left)  # type: ignore
            right_is_owner = not any(var is None for var in right) and all(variable_is_owner(var) for var in right)  # type: ignore

            if check_only_eoa:
                if left_is_msg_sender and expression_is_global_symbol(
                    expression.right_expression, GlobalSymbol.TX_ORIGIN
                ):
                    return True
                if right_is_msg_sender and expression_is_global_symbol(
                    expression.left_expression, GlobalSymbol.TX_ORIGIN
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
                if expression_is_global_symbol(arg_expr, GlobalSymbol.MSG_SENDER):
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
        possible_owners = get_variable_declarations_from_expression(
            expression.base_expression
        )
        index_vars = get_variable_declarations_from_expression(
            expression.index_expression
        )
        index_is_msg_sender = (
            len(index_vars) == 1 and index_vars[0] in msg_sender_variables
        ) or expression_is_global_symbol(
            expression.index_expression, GlobalSymbol.MSG_SENDER
        )
        if (
            not any(var is None for var in possible_owners)
            and all(variable_is_owner(var) for var in possible_owners)  # type: ignore
            and index_is_msg_sender
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


def statement_is_only_owner(
    statement: Union[StatementAbc, YulStatementAbc], check_only_eoa: bool
) -> bool:
    if not isinstance(statement, ExpressionStatement):
        return False
    expr = statement.expression
    if isinstance(expr, FunctionCall):
        function_called = expr.function_called
        if (
            isinstance(function_called, FunctionDefinition)
            and function_called.body is not None
        ):
            cfg = function_called.cfg
            assert cfg is not None
            return not _cfg_block_or_statement_is_publicly_reachable(
                cfg.success_end_node,
                cfg,
                check_func_visibility=False,
                check_only_eoa=check_only_eoa,
            )
    return False


@cached_return_on_recursion(False)
def _cfg_block_or_statement_is_publicly_reachable(
    target: Union[CfgNode, StatementAbc],
    cfg: ControlFlowGraph,
    check_func_visibility: bool = True,
    check_only_eoa: bool = False,
) -> bool:
    decl = cfg.declaration
    assert not isinstance(decl, YulFunctionDefinition), "Yul not supported"

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

    if isinstance(target, StatementAbc):
        block = cfg.get_cfg_node(target)
        if target not in block.statements:
            assert target == block.control_statement
            if any(
                statement_is_only_owner(s, check_only_eoa) for s in block.statements
            ):
                return False
        else:
            index = block.statements.index(target)
            if any(
                statement_is_only_owner(s, check_only_eoa)
                for s in block.statements[:index]
            ):
                return False
    elif isinstance(target, CfgNode):
        block = target
    else:
        raise NotImplementedError()

    if block == cfg.start_node:
        reached_start = True
    else:
        graph = cfg.graph
        visited = {block}
        queue = deque([block])
        reached_start = False

        while len(queue) > 0:
            block = queue.popleft()
            from_: CfgNode
            condition: Tuple[TransitionConditionKind, Optional[ExpressionAbc]]
            for (
                from_,
                _,
                data,
            ) in graph.in_edges(  # pyright: ignore reportGeneralTypeIssues
                block, data=True  # pyright: ignore reportGeneralTypeIssues
            ):
                if from_ in visited:
                    continue
                condition = data["condition"]  # pyright: ignore reportOptionalSubscript
                if (
                    (condition[0] == TransitionConditionKind.NEVER)
                    or (
                        condition[0] == TransitionConditionKind.IS_TRUE
                        and condition[1] is not None
                        and expression_is_only_owner(
                            condition[1],  # pyright: ignore reportGeneralTypeIssues
                            set(),
                            check_only_eoa=check_only_eoa,
                        )
                    )
                    or (
                        condition[0] == TransitionConditionKind.IS_FALSE
                        and condition[1] is not None
                        and expression_is_only_owner(
                            condition[1],  # pyright: ignore reportGeneralTypeIssues
                            set(),
                            check_only_eoa=check_only_eoa,
                            inverted=True,
                        )
                    )
                ):
                    continue

                if any(
                    statement_is_only_owner(s, check_only_eoa) for s in from_.statements
                ):
                    continue

                if from_ == cfg.start_node:
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

    for ref in decl.get_all_references(False):
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


def statement_is_publicly_executable(
    statement: StatementAbc,
    check_func_visibility: bool = True,
    check_only_eoa: bool = False,
) -> bool:
    return _cfg_block_or_statement_is_publicly_reachable(
        statement,
        statement.declaration.cfg,
        check_func_visibility=check_func_visibility,
        check_only_eoa=check_only_eoa,
    )


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


def address_is_safe(addr: VariableDeclaration) -> Optional[bool]:
    if variable_is_owner(addr):
        return True

    if isinstance(addr.parent, ParameterList) and (
        isinstance(addr.parent.parent, FunctionDefinition)
    ):
        function_definition = addr.parent.parent
        assert isinstance(function_definition, FunctionDefinition)
        if function_definition.visibility in {
            Visibility.PUBLIC,
            Visibility.EXTERNAL,
        }:
            return False

        return None
    elif addr.is_state_variable:
        if addr.mutability in {
            Mutability.CONSTANT,
            Mutability.IMMUTABLE,
        }:
            return True
        return False
    elif isinstance(addr.parent, VariableDeclarationStatement):
        return None
    else:
        logger.warning(
            f"Unable to detect if address source is safe: {addr.parent}\n{addr.source}"
        )
        return None
