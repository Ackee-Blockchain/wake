from __future__ import annotations

from functools import reduce
from operator import or_
from typing import TYPE_CHECKING, Iterator, List, Set, Tuple, Union

from wake.ir.ast import SolcYulFunctionCall, SolcYulIdentifier, SolcYulLiteral
from wake.ir.utils import IrInitTuple

from ...utils import cached_return_on_recursion
from ..enums import ModifiesStateFlag, YulLiteralKind
from .abc import YulAbc
from .block import YulBlock
from .function_definition import YulFunctionDefinition
from .identifier import YulIdentifier
from .literal import YulLiteral

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
    from .assignment import YulAssignment
    from .expression_statement import YulExpressionStatement
    from .for_loop import YulForLoop
    from .if_statement import YulIf
    from .switch import YulSwitch
    from .variable_declaration import YulVariableDeclaration


class YulFunctionCall(YulAbc):
    """
    Represents a call to a "builtin" function/instruction (see [Solidity docs](https://docs.soliditylang.org/en/latest/yul.html#evm-dialect)) or a user-defined [YulFunctionDefinition][wake.ir.yul.function_definition.YulFunctionDefinition].

    !!! example
        `foo` and `stop()` in the following example:

        ```solidity
        assembly {
            function foo() -> x, y {
                x := 1
                y := 2
            }
            foo()
            stop()
        }
        ```
    """

    _parent: Union[
        YulAssignment,
        YulExpressionStatement,
        YulForLoop,
        YulIf,
        YulSwitch,
        YulVariableDeclaration,
        YulFunctionCall,
    ]
    _arguments: List[Union[YulFunctionCall, YulIdentifier, YulLiteral]]
    _function_name: YulIdentifier

    def __init__(
        self, init: IrInitTuple, function_call: SolcYulFunctionCall, parent: YulAbc
    ):
        super().__init__(init, function_call, parent)
        self._function_name = YulIdentifier(init, function_call.function_name, self)
        self._arguments = []
        for argument in function_call.arguments:
            if isinstance(argument, SolcYulFunctionCall):
                self._arguments.append(
                    YulFunctionCall(
                        init, argument, self  # pyright: ignore reportGeneralTypeIssues
                    )
                )
            elif isinstance(argument, SolcYulIdentifier):
                self._arguments.append(
                    YulIdentifier(
                        init, argument, self  # pyright: ignore reportGeneralTypeIssues
                    )
                )
            elif isinstance(argument, SolcYulLiteral):
                self._arguments.append(
                    YulLiteral(
                        init, argument, self  # pyright: ignore reportGeneralTypeIssues
                    )
                )
            else:
                assert False, f"Unexpected type: {type(argument)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._function_name
        for argument in self._arguments:
            yield from argument

    @property
    def parent(
        self,
    ) -> Union[
        YulAssignment,
        YulExpressionStatement,
        YulForLoop,
        YulIf,
        YulSwitch,
        YulVariableDeclaration,
        YulFunctionCall,
    ]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def arguments(
        self,
    ) -> Tuple[Union[YulFunctionCall, YulIdentifier, YulLiteral], ...]:
        """
        Returns:
            Arguments of the function call in the order they appear in the source code.
        """
        return tuple(self._arguments)

    @property
    def function_name(self) -> YulIdentifier:
        """
        Returns:
            Name of the function that is called.
        """
        return self._function_name

    @property
    @cached_return_on_recursion(frozenset())
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        ret = set()

        if self._function_name.name == "sstore":
            ret.add((self, ModifiesStateFlag.MODIFIES_STATE_VAR))
        elif self._function_name.name in {"create", "create2"}:
            ret.add((self, ModifiesStateFlag.DEPLOYS_CONTRACT))
        elif self._function_name.name in {"call", "callcode"}:
            arg2 = self._arguments[2]
            if (
                isinstance(arg2, YulLiteral)
                and arg2.kind == YulLiteralKind.NUMBER
                and arg2.value is not None
                and (
                    int(arg2.value, 16)
                    if arg2.value.startswith("0x")
                    else int(arg2.value)
                )
                == 0
            ):
                # value is 0
                pass
            else:
                ret.add((self, ModifiesStateFlag.SENDS_ETHER))
            ret.add((self, ModifiesStateFlag.PERFORMS_CALL))
        elif self._function_name.name == "delegatecall":
            ret.add((self, ModifiesStateFlag.PERFORMS_DELEGATECALL))
        elif self._function_name.name == "selfdestruct":
            ret.add((self, ModifiesStateFlag.SELFDESTRUCTS))
        elif self._function_name.name in {
            "log0",
            "log1",
            "log2",
            "log3",
            "log4",
        }:
            ret.add((self, ModifiesStateFlag.EMITS))
        else:
            # try to find YulFunctionDefinition in parents
            parent = self.parent
            while parent != self.inline_assembly:
                if isinstance(parent, YulBlock):
                    try:
                        func = next(
                            s
                            for s in parent.statements
                            if isinstance(s, YulFunctionDefinition)
                            and s.name == self._function_name.name
                        )
                        ret |= func.body.modifies_state
                        break
                    except StopIteration:
                        pass
                parent = parent.parent

        ret |= reduce(
            or_,
            (argument.modifies_state for argument in self.arguments),
            set(),
        )

        return ret
