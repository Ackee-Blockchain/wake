from __future__ import annotations

from typing import TYPE_CHECKING, Set, Tuple, Union

from wake.ir.ast import SolcYulTypedName
from wake.ir.utils import IrInitTuple

from ..enums import ModifiesStateFlag
from .abc import YulAbc

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
    from .function_definition import YulFunctionDefinition
    from .variable_declaration import YulVariableDeclaration


class YulTypedName(YulAbc):
    """
    As opposed to [YulIdentifier][wake.ir.yul.identifier.YulIdentifier] that serves as a reference to a variable and is evaluated to its value, `YulTypedName` is a declaration of a variable (an intention to use the given name for a variable).

    The difference from [YulVariableDeclaration][wake.ir.yul.variable_declaration.YulVariableDeclaration] is that the variable declaration is used to declare a new unique name and contains `YulTypedName` as a child.

    !!! example
        `x`, `y`, `z` and `w` in the following example are all typed names:

        ```solidity
        assembly {
            function foo(x, y) -> z {
                z := add(x, y)
            }
            let w := foo(1, 2)
        }
        ```
    """

    _parent: Union[YulFunctionDefinition, YulVariableDeclaration]
    _name: str
    _type: str

    def __init__(self, init: IrInitTuple, typed_name: SolcYulTypedName, parent: YulAbc):
        super().__init__(init, typed_name, parent)
        self._name = typed_name.name
        self._type = typed_name.type
        assert (
            self._type == ""
        ), f"Expected YulTypedName type to be empty, got {self._type}"

    @property
    def parent(self) -> Union[YulFunctionDefinition, YulVariableDeclaration]:
        return self._parent

    @property
    def name(self) -> str:
        """
        Returns:
            Name of the typed name.
        """
        return self._name

    # type seems to be always empty
    # @property
    # def type(self) -> str:
    # return self._type

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return set()
