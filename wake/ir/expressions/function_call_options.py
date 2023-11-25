from __future__ import annotations

from functools import lru_cache, reduce
from operator import or_
from typing import TYPE_CHECKING, Iterator, List, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcFunctionCallOptions
from wake.ir.enums import ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..statements.abc import StatementAbc
    from ..yul.abc import YulAbc


class FunctionCallOptions(ExpressionAbc):
    """
    Sets `gas`, `value` and `salt` function call options.

    Serves as a replacement for old-style syntax, e.g. `:::solidity this.foo.gas(1000).value(1)()`.

    !!! example
        `:::solidity this.foo{gas: 1000, value: 1}` in the following example:
        ```solidity
        function foo() public {
            this.foo{gas: 1000, value: 1}();
        }
        ```
    """

    _ast_node: SolcFunctionCallOptions
    _parent: SolidityAbc  # TODO: make this more specific

    _expression: ExpressionAbc
    _names: List[str]
    _options: List[ExpressionAbc]

    def __init__(
        self,
        init: IrInitTuple,
        function_call_options: SolcFunctionCallOptions,
        parent: SolidityAbc,
    ):
        super().__init__(init, function_call_options, parent)
        self._expression = ExpressionAbc.from_ast(
            init, function_call_options.expression, self
        )
        self._names = list(function_call_options.names)
        self._options = [
            ExpressionAbc.from_ast(init, option, self)
            for option in function_call_options.options
        ]

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._expression
        for option in self._options:
            yield from option

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def expression(self) -> ExpressionAbc:
        """
        !!! example
            `:::solidity address(this).call` and `:::solidity new MyToken` in the following example:

            ```solidity
            function f() public {
                address(this).call{value: 1}("");
                new MyToken{salt: 0x1234}();
            }
            ```

        Returns:
            Sub-expression the function call options are applied to.
        """
        return self._expression

    @property
    def names(self) -> Tuple[str, ...]:
        """
        Returns:
            Names of the function call options in the order they appear in the source code.
        """
        return tuple(self._names)

    @property
    def options(self) -> Tuple[ExpressionAbc, ...]:
        """
        Returns:
            Values of the function call options in the order they appear in the source code.
        """
        return tuple(self._options)

    @property
    def is_ref_to_state_variable(self) -> bool:
        return False

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        ret = self.expression.modifies_state | reduce(
            or_,
            (option.modifies_state for option in self.options),
            set(),
        )
        if "value" in self.names:
            ret |= {(self, ModifiesStateFlag.SENDS_ETHER)}
        return ret
