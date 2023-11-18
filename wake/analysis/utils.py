from collections import deque
from typing import Deque, Set, Tuple, Union, overload

from wake.core import get_logger
from wake.ir import (
    ExpressionAbc,
    FunctionCall,
    FunctionCallOptions,
    FunctionDefinition,
    MemberAccess,
    ModifierDefinition,
    StructDefinition,
    VariableDeclaration,
)

logger = get_logger(__name__)


def pair_function_call_arguments(
    definition: Union[FunctionDefinition, StructDefinition], call: FunctionCall
) -> Tuple[Tuple[VariableDeclaration, ExpressionAbc], ...]:
    """
    Pairs function call arguments with function/struct definition parameters.
    Returned pairs are in the same order as the function definition parameters.

    !!! example
        The function also handles calls of bounded functions with the `using for` directive.

        ```solidity
        contract C {
            using SafeERC20 for IERC20;

            function withdraw(IERC20 token, uint256 amount) external {
                token.safeTransfer(msg.sender, amount); // token is the first argument of safeTransfer
            }
        }
        ```

    Args:
        definition: Function or struct definition called.
        call: Function call or struct constructor call.

    Returns:
        Tuple of pairs of function/struct definition parameters and function call arguments.
    """
    assert len(call.names) == 0 or len(call.names) == len(
        call.arguments
    ), "Call names must be empty or same length as arguments"

    vars = (
        definition.parameters.parameters
        if isinstance(definition, FunctionDefinition)
        else definition.members
    )

    if len(vars) == len(call.arguments):
        if len(call.names) == 0:
            return tuple(zip(vars, call.arguments))
        else:
            return tuple((p, call.arguments[call.names.index(p.name)]) for p in vars)
    elif len(vars) == len(call.arguments) + 1:
        # using for
        node = call.expression
        if isinstance(node, FunctionCallOptions):
            node = node.expression
        if isinstance(node, MemberAccess):
            node = node.expression

        if len(call.names) == 0:
            return ((vars[0], node),) + tuple(zip(vars[1:], call.arguments))
        else:
            return ((vars[0], node),) + tuple(
                (p, call.arguments[call.names.index(p.name)]) for p in vars[1:]
            )
    else:
        raise ValueError(
            f"{definition.name} has {len(vars)} parameters but called with {len(call.arguments)} arguments"
        )


@overload
def get_all_base_and_child_declarations(
    declaration: FunctionDefinition,
    *,
    base: bool = True,
    child: bool = True,
) -> Set[Union[FunctionDefinition, VariableDeclaration]]:
    ...


@overload
def get_all_base_and_child_declarations(
    declaration: VariableDeclaration,
    *,
    base: bool = True,
    child: bool = True,
) -> Set[Union[FunctionDefinition, VariableDeclaration]]:
    ...


@overload
def get_all_base_and_child_declarations(
    declaration: ModifierDefinition,
    *,
    base: bool = True,
    child: bool = True,
) -> Set[ModifierDefinition]:
    ...


def get_all_base_and_child_declarations(
    declaration: Union[FunctionDefinition, ModifierDefinition, VariableDeclaration],
    *,
    base: bool = True,
    child: bool = True,
) -> Union[
    Set[Union[FunctionDefinition, VariableDeclaration]], Set[ModifierDefinition]
]:
    """
    Args:
        declaration: Declaration to get base and child declarations of.
        base: Return base declarations of the given declaration.
        child: Return child declarations of the given declaration.

    Returns:
        Recursively all base and child declarations of the given declaration plus the given declaration itself.

            Set of [ModifierDefinitions][wake.ir.declarations.modifier_definition.ModifierDefinition] is returned for [ModifierDefinition][wake.ir.declarations.modifier_definition.ModifierDefinition] input,
            otherwise set of [FunctionDefinitions][wake.ir.declarations.function_definition.FunctionDefinition] and [VariableDeclarations][wake.ir.declarations.variable_declaration.VariableDeclaration] is returned.
    """
    ret = {declaration}
    queue: Deque[
        Union[FunctionDefinition, ModifierDefinition, VariableDeclaration]
    ] = deque([declaration])

    while len(queue) > 0:
        declaration = queue.popleft()

        if isinstance(declaration, VariableDeclaration):
            for base_func in declaration.base_functions:
                if base and base_func not in ret:
                    ret.add(base_func)
                    queue.append(base_func)
        elif isinstance(declaration, FunctionDefinition):
            for base_func in declaration.base_functions:
                if base and base_func not in ret:
                    ret.add(base_func)
                    queue.append(base_func)
            for child_func in declaration.child_functions:
                if child and child_func not in ret:
                    ret.add(child_func)
                    queue.append(child_func)
        elif isinstance(declaration, ModifierDefinition):
            for base_mod in declaration.base_modifiers:
                if base and base_mod not in ret:
                    ret.add(base_mod)
                    queue.append(base_mod)
            for child_mod in declaration.child_modifiers:
                if child and child_mod not in ret:
                    ret.add(child_mod)
                    queue.append(child_mod)
    return ret  # pyright: ignore reportGeneralTypeIssues


@overload
def get_function_implementations(
    function: FunctionDefinition,
    *,
    variables: bool = True,
) -> Set[Union[FunctionDefinition, VariableDeclaration]]:
    ...


@overload
def get_function_implementations(
    function: FunctionDefinition,
    *,
    variables: bool = False,
) -> Set[FunctionDefinition]:
    ...


def get_function_implementations(  # pyright: ignore reportGeneralTypeIssues
    function: FunctionDefinition,
    *,
    variables: bool = True,
) -> Set[Union[FunctionDefinition, VariableDeclaration]]:
    """
    Also returns the given function if it is implemented.

    Args:
        function: Function to get implementations of.
        variables: Include variable declarations in the returned set.

    Returns:
        All overridden implemented functions and variable declarations of the given function.
    """
    ret = set()

    for child in get_all_base_and_child_declarations(function, base=False):
        if isinstance(child, VariableDeclaration):
            if variables:
                ret.add(child)
        else:
            if child.implemented:
                ret.add(child)

    return ret  # pyright: ignore reportGeneralTypeIssues


def get_modifier_implementations(
    modifier: ModifierDefinition,
) -> Set[ModifierDefinition]:
    """
    Also returns the given modifier if it is implemented.

    Args:
        modifier: Modifier to get implementations of.

    Returns:
        All overridden implemented modifiers of the given modifier.
    """
    ret = set()

    for child in get_all_base_and_child_declarations(modifier, base=False):
        if child.implemented:
            ret.add(child)

    return ret
