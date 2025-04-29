from enum import IntFlag
from functools import reduce
from operator import or_
from typing import Set, Tuple, Union

import wake.ir as ir
from wake.utils import dict_cached_return_on_recursion


class ModifiesStateFlag(IntFlag):
    """
    Flag enum describing how an expression ([ExpressionAbc][wake.ir.expressions.abc.ExpressionAbc]) or statement ([StatementAbc][wake.ir.statements.abc.StatementAbc]) modifies the blockchain state.
    """

    MODIFIES_STATE_VAR = 1
    EMITS = 2
    SENDS_ETHER = 4
    DEPLOYS_CONTRACT = 8
    SELFDESTRUCTS = 16
    PERFORMS_CALL = 32
    PERFORMS_DELEGATECALL = 64
    CALLS_UNIMPLEMENTED_NONPAYABLE_FUNCTION = 128
    CALLS_UNIMPLEMENTED_PAYABLE_FUNCTION = 256

    def __repr__(self):
        if self.value == 0:
            return f"{self.__class__.__name__}(0)"
        flags = [f for f in self.__class__ if f in self]
        return " | ".join(f.name or "" for f in flags)

    __str__ = __repr__


# TODO state var references


def _handle_assignment(
    node: ir.Assignment,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    ret = modifies_state(node.left_expression) | modifies_state(node.right_expression)
    if node.left_expression.is_ref_to_state_variable:
        ret |= {(node, ModifiesStateFlag.MODIFIES_STATE_VAR)}
    return ret


def _handle_binary_operation(
    node: ir.BinaryOperation,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.left_expression) | modifies_state(node.right_expression)


def _handle_conditional(
    node: ir.Conditional,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return (
        modifies_state(node.condition)
        | modifies_state(node.true_expression)
        | modifies_state(node.false_expression)
    )


def _handle_function_call_options(
    node: ir.FunctionCallOptions,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    ret = modifies_state(node.expression) | reduce(
        or_,
        (modifies_state(option) for option in node.options),
        set(),
    )
    if "value" in node.names:
        ret |= {(node, ModifiesStateFlag.SENDS_ETHER)}
    return ret


def _collect_called_functions(
    node: ir.ExpressionAbc,
) -> set:
    if isinstance(node, (ir.Identifier, ir.MemberAccess)):
        return {node.referenced_declaration}
    elif isinstance(node, ir.FunctionCall):
        node = node.expression
        while isinstance(node, ir.MemberAccess) and node.referenced_declaration in {
            ir.enums.GlobalSymbol.FUNCTION_VALUE,
            ir.enums.GlobalSymbol.FUNCTION_GAS,
        }:
            node = node.expression
        return _collect_called_functions(node)
    elif isinstance(node, ir.FunctionCallOptions):
        return _collect_called_functions(node.expression)
    elif isinstance(node, ir.NewExpression):
        return set()  # TODO
    elif isinstance(node, ir.TupleExpression):
        if len(node.components) != 1 or node.components[0] is None:
            return set()
        return _collect_called_functions(node.components[0])
    elif isinstance(node, ir.Conditional):
        return _collect_called_functions(
            node.true_expression
        ) | _collect_called_functions(node.false_expression)
    else:
        return set()


def _handle_function_call(
    node: ir.FunctionCall,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    ret = modifies_state(node.expression) | reduce(
        or_,
        (modifies_state(argument) for argument in node.arguments),
        set(),
    )

    if node.kind == ir.enums.FunctionCallKind.FUNCTION_CALL:
        called_functions = _collect_called_functions(node)
        if (
            ir.enums.GlobalSymbol.SELFDESTRUCT in called_functions
            or ir.enums.GlobalSymbol.SUICIDE in called_functions
        ):
            ret |= {(node, ModifiesStateFlag.SELFDESTRUCTS)}
        elif (
            ir.enums.GlobalSymbol.ADDRESS_TRANSFER in called_functions
            or ir.enums.GlobalSymbol.ADDRESS_SEND in called_functions
        ):
            ret |= {(node, ModifiesStateFlag.SENDS_ETHER)}
        elif ir.enums.GlobalSymbol.ADDRESS_CALL in called_functions:
            ret |= {(node, ModifiesStateFlag.PERFORMS_CALL)}
        elif ir.enums.GlobalSymbol.ADDRESS_DELEGATECALL in called_functions:
            ret |= {(node, ModifiesStateFlag.PERFORMS_DELEGATECALL)}
        elif (
            ir.enums.GlobalSymbol.ARRAY_PUSH in called_functions
            or ir.enums.GlobalSymbol.ARRAY_POP in called_functions
            or ir.enums.GlobalSymbol.BYTES_PUSH in called_functions
            or ir.enums.GlobalSymbol.BYTES_POP in called_functions
        ):
            ret |= {(node, ModifiesStateFlag.MODIFIES_STATE_VAR)}
        elif ir.enums.GlobalSymbol.FUNCTION_VALUE in called_functions:
            ret |= {
                (node, ModifiesStateFlag.SENDS_ETHER)
            }  # TODO .value() itself does nothing

        for func in called_functions:
            if isinstance(func, ir.ContractDefinition):
                continue  # TODO contract constructor + modifiers

            if not isinstance(func, ir.FunctionDefinition):
                continue
            if func.state_mutability in {
                ir.enums.StateMutability.PURE,
                ir.enums.StateMutability.VIEW,
            }:
                continue

            # TODO get all child and base implementations
            if func.body is not None:
                ret |= modifies_state(func.body)
                for modifier in func.modifiers:
                    modifier_def = modifier.modifier_name.referenced_declaration
                    # TODO get all child and base implementations
                    assert isinstance(modifier_def, ir.ModifierDefinition)
                    if modifier_def.body is not None:
                        ret |= modifies_state(modifier_def.body)
            elif func.state_mutability == ir.enums.StateMutability.NONPAYABLE:
                ret |= {
                    (
                        node,
                        ModifiesStateFlag.CALLS_UNIMPLEMENTED_NONPAYABLE_FUNCTION,
                    )
                }
            elif func.state_mutability == ir.enums.StateMutability.PAYABLE:
                ret |= {
                    (
                        node,
                        ModifiesStateFlag.CALLS_UNIMPLEMENTED_PAYABLE_FUNCTION,
                    )
                }
            else:
                assert False
    return ret


def _handle_index_access(
    node: ir.IndexAccess,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    ret = modifies_state(node.base_expression)
    if node.index_expression is not None:
        ret |= modifies_state(node.index_expression)
    return ret


def _handle_index_range_access(
    node: ir.IndexRangeAccess,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    ret = modifies_state(node.base_expression)
    if node.start_expression is not None:
        ret |= modifies_state(node.start_expression)
    if node.end_expression is not None:
        ret |= modifies_state(node.end_expression)
    return ret


def _handle_member_access(
    node: ir.MemberAccess,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.expression)


def _handle_new_expression(
    node: ir.NewExpression,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    if isinstance(node.type, ir.types.Contract):
        # TODO contract constructor + modifiers
        return {(node, ModifiesStateFlag.DEPLOYS_CONTRACT)}
    else:
        return set()


def _handle_tuple_expression(
    node: ir.TupleExpression,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return reduce(
        or_,
        (
            modifies_state(component)
            for component in node.components
            if component is not None
        ),
        set(),
    )


def _handle_unary_operation(
    node: ir.UnaryOperation,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    ret = modifies_state(node.sub_expression)

    if (
        node.operator
        in {
            ir.enums.UnaryOpOperator.PLUS_PLUS,
            ir.enums.UnaryOpOperator.MINUS_MINUS,
            ir.enums.UnaryOpOperator.DELETE,
        }
        and node.sub_expression.is_ref_to_state_variable
    ):
        ret |= {(node, ModifiesStateFlag.MODIFIES_STATE_VAR)}

    return ret


def _handle_block(
    node: ir.Block,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return reduce(
        or_,
        (modifies_state(statement) for statement in node.statements),
        set(),
    )


def _handle_do_while_statement(
    node: ir.DoWhileStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.body) | modifies_state(node.condition)


def _handle_emit_statement(
    node: ir.EmitStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return {(node, ModifiesStateFlag.EMITS)} | modifies_state(node.event_call)


def _handle_expression_statement(
    node: ir.ExpressionStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.expression)


def _handle_for_statement(
    node: ir.ForStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    ret = set()
    if node.initialization_expression is not None:
        ret |= modifies_state(node.initialization_expression)
    if node.condition is not None:
        ret |= modifies_state(node.condition)
    if node.loop_expression is not None:
        ret |= modifies_state(node.loop_expression)
    ret |= modifies_state(node.body)
    return ret


def _handle_if_statement(
    node: ir.IfStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return (
        modifies_state(node.condition)
        | modifies_state(node.true_body)
        | (modifies_state(node.false_body) if node.false_body is not None else set())
    )


def _handle_inline_assembly(
    node: ir.InlineAssembly,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.yul_block)


def _handle_return_statement(
    node: ir.Return,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    if node.expression is None:
        return set()
    return modifies_state(node.expression)


def _handle_revert_statement(
    node: ir.RevertStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.error_call)


def _handle_try_statement(
    node: ir.TryStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return reduce(
        or_,
        (modifies_state(clause.block) for clause in node.clauses),
        set(),
    ) | modifies_state(node.external_call)


def _handle_unchecked_block(
    node: ir.UncheckedBlock,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return reduce(
        or_,
        (modifies_state(statement) for statement in node.statements),
        set(),
    )


def _handle_variable_declaration_statement(
    node: ir.VariableDeclarationStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    ret = set()
    if node.initial_value is not None:
        ret |= modifies_state(node.initial_value)
        if any(
            declaration.is_state_variable
            for declaration in node.declarations
            if declaration is not None
        ):
            ret |= {(node, ModifiesStateFlag.MODIFIES_STATE_VAR)}
    return ret


def _handle_while_statement(
    node: ir.WhileStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.body) | modifies_state(node.condition)


def _handle_yul_assignment(
    node: ir.YulAssignment,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    # TODO assignment to state/transient var?
    return modifies_state(node.value)


def _handle_yul_block(
    node: ir.YulBlock,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return reduce(
        or_,
        (modifies_state(statement) for statement in node.statements),
        set(),
    )


def _handle_yul_case(
    node: ir.YulCase,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.body)


def _handle_yul_expression_statement(
    node: ir.YulExpressionStatement,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.expression)


def _handle_yul_for_loop(
    node: ir.YulForLoop,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return (
        modifies_state(node.pre)
        | modifies_state(node.condition)
        | modifies_state(node.post)
        | modifies_state(node.body)
    )


def _handle_yul_function_call(
    node: ir.YulFunctionCall,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    # TODO transient state?
    ret = set()
    if node.function_name.name == "sstore":
        ret.add((node, ModifiesStateFlag.MODIFIES_STATE_VAR))
    elif node.function_name.name in {"create", "create2"}:
        ret.add((node, ModifiesStateFlag.DEPLOYS_CONTRACT))
    elif node.function_name.name in {"call", "callcode"}:
        arg2 = node.arguments[2]
        if (
            isinstance(arg2, ir.YulLiteral)
            and arg2.kind == ir.enums.YulLiteralKind.NUMBER
            and arg2.value is not None
            and (
                int(arg2.value, 16) if arg2.value.startswith("0x") else int(arg2.value)
            )
            == 0
        ):
            # value is 0
            pass
        else:
            ret.add((node, ModifiesStateFlag.SENDS_ETHER))
        ret.add((node, ModifiesStateFlag.PERFORMS_CALL))
    elif node.function_name.name == "delegatecall":
        ret.add((node, ModifiesStateFlag.PERFORMS_DELEGATECALL))
    elif node.function_name.name == "selfdestruct":
        ret.add((node, ModifiesStateFlag.SELFDESTRUCTS))
    elif node.function_name.name in {
        "log0",
        "log1",
        "log2",
        "log3",
        "log4",
    }:
        ret.add((node, ModifiesStateFlag.EMITS))
    else:
        # try to find YulFunctionDefinition in parents
        parent = node.parent
        while parent != node.inline_assembly:
            if isinstance(parent, ir.YulBlock):
                try:
                    func = next(
                        s
                        for s in parent.statements
                        if isinstance(s, ir.YulFunctionDefinition)
                        and s.name == node.function_name.name
                    )
                    ret |= modifies_state(func.body)
                    break
                except StopIteration:
                    pass
            parent = parent.parent

    ret |= reduce(
        or_,
        (modifies_state(argument) for argument in node.arguments),
        set(),
    )
    return ret


def _handle_yul_if(
    node: ir.YulIf,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.condition) | modifies_state(node.body)


def _handle_yul_switch(
    node: ir.YulSwitch,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    return modifies_state(node.expression) | reduce(
        or_,
        (modifies_state(case) for case in node.cases),
        set(),
    )


def _handle_yul_variable_declaration(
    node: ir.YulVariableDeclaration,
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    if node.value is not None:
        return modifies_state(node.value)
    return set()


_handlers = {
    ir.Assignment: _handle_assignment,
    ir.BinaryOperation: _handle_binary_operation,
    ir.Conditional: _handle_conditional,
    # ir.ElementaryTypeNameExpression - no state changes
    ir.FunctionCallOptions: _handle_function_call_options,
    ir.FunctionCall: _handle_function_call,
    # ir.Identifier - no state changes
    ir.IndexAccess: _handle_index_access,
    ir.IndexRangeAccess: _handle_index_range_access,
    # ir.Literal - no state changes
    ir.MemberAccess: _handle_member_access,
    ir.NewExpression: _handle_new_expression,
    ir.TupleExpression: _handle_tuple_expression,
    ir.UnaryOperation: _handle_unary_operation,
    # ir.TryCatchClause - handled in _handle_try_statement
    ir.Block: _handle_block,
    # ir.Break - no state changes
    # ir.Continue - no state changes
    ir.DoWhileStatement: _handle_do_while_statement,
    ir.EmitStatement: _handle_emit_statement,
    ir.ExpressionStatement: _handle_expression_statement,
    ir.ForStatement: _handle_for_statement,
    ir.IfStatement: _handle_if_statement,
    ir.InlineAssembly: _handle_inline_assembly,
    # ir.PlaceholderStatement - no state changes
    ir.Return: _handle_return_statement,
    ir.RevertStatement: _handle_revert_statement,
    ir.TryStatement: _handle_try_statement,
    ir.UncheckedBlock: _handle_unchecked_block,
    ir.VariableDeclarationStatement: _handle_variable_declaration_statement,
    ir.WhileStatement: _handle_while_statement,
    ir.YulAssignment: _handle_yul_assignment,
    ir.YulBlock: _handle_yul_block,
    # ir.YulBreak - no state changes
    ir.YulCase: _handle_yul_case,
    # ir.YulContinue - no state changes
    ir.YulExpressionStatement: _handle_yul_expression_statement,
    ir.YulForLoop: _handle_yul_for_loop,
    ir.YulFunctionCall: _handle_yul_function_call,
    # ir.YulFunctionDefinition - no state changes
    # ir.YulIdentifier - no state changes
    ir.YulIf: _handle_yul_if,
    # ir.YulLeave - no state changes
    # ir.YulLiteral - no state changes
    ir.YulSwitch: _handle_yul_switch,
    ir.YulVariableDeclaration: _handle_yul_variable_declaration,
}


@dict_cached_return_on_recursion(frozenset())
def modifies_state(
    node: Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc],
) -> Set[Tuple[Union[ir.ExpressionAbc, ir.StatementAbc, ir.YulAbc], ModifiesStateFlag]]:
    try:
        return _handlers[type(node)](node)
    except KeyError:
        return set()
