from __future__ import annotations

from typing import Iterator, Optional, Union, TYPE_CHECKING

from ...types import Array

if TYPE_CHECKING:
    from ..declaration.variable_declaration import VariableDeclaration
    from ..expression.new_expression import NewExpression
    from ..meta.using_for_directive import UsingForDirective
    from .mapping import Mapping

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcArrayTypeName


class ArrayTypeName(TypeNameAbc):
    """
    Array type name.

    !!! example
        An array type name can be used:

        - inside a [VariableDeclaration][woke.ast.ir.declaration.variable_declaration.VariableDeclaration]:
            - `:::solidity bool[]` in line 1,
            - `:::solidity int[10][20]` in line 11,
            - `:::solidity string[10]` in line 12,
            - `:::solidity address[]` in line 16,
        - inside a [NewExpression][woke.ast.ir.expression.new_expression.NewExpression]:
            - `:::solidity address[]` in line 16,
        - inside a [UsingForDirective][woke.ast.ir.meta.using_for_directive.UsingForDirective]:
            - `:::solidity bool[]` in line 8,
        - inside an [ArrayTypeName][woke.ast.ir.type_name.array_type_name.ArrayTypeName]:
            - `:::solidity int[10]` in line 11,
        - inside a [Mapping][woke.ast.ir.type_name.mapping.Mapping]:
            - `:::solidity C[]` in line 13.

        ```solidity linenums="1"
        function or(bool[] memory arr) pure returns(bool) {
            for (uint i = 0; i < arr.length; i++)
                if (arr[i])
                    return true;
            return false;
        }

        using {or} for bool[];

        contract C {
            int[10][20] arr;
            string[10] names;
            mapping(address => C[]) map;

            function foo() public pure {
                address[] memory addresses = new address[](5);
            }
        }
        ```
    """
    _ast_node: SolcArrayTypeName
    _parent: Union[VariableDeclaration, NewExpression, UsingForDirective, ArrayTypeName, Mapping]

    _base_type: TypeNameAbc
    _length: Optional[ExpressionAbc]

    def __init__(
        self, init: IrInitTuple, array_type_name: SolcArrayTypeName, parent: SolidityAbc
    ):
        super().__init__(init, array_type_name, parent)
        self._base_type = TypeNameAbc.from_ast(init, array_type_name.base_type, self)
        self._length = (
            ExpressionAbc.from_ast(init, array_type_name.length, self)
            if array_type_name.length
            else None
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._base_type
        if self._length is not None:
            yield from self._length

    @property
    def parent(self) -> Union[VariableDeclaration, NewExpression, UsingForDirective, ArrayTypeName, Mapping]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def type(self) -> Array:
        """
        Returns:
            Type description.
        """
        t = super().type
        assert isinstance(t, Array)
        return t

    @property
    def base_type(self) -> TypeNameAbc:
        """
        !!! example
            `uint8[2]` has `uint8` ([ElementaryTypeName][woke.ast.ir.type_name.elementary_type_name.ElementaryTypeName]) as a base type.

            `uint8[2][3]` has `uint8[2]` ([ArrayTypeName][woke.ast.ir.type_name.array_type_name.ArrayTypeName]) as a base type.
        Returns:
            Type name IR node describing the base type.
        """
        return self._base_type

    @property
    def length(self) -> Optional[ExpressionAbc]:
        """
        Returns an expression as present in the source code.
        Returns:
            Expression defining the length of the array.
        """
        return self._length
