from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition
    from ..meta.source_unit import SourceUnit

from woke.ast.ir.abc import IrAbc, TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcUserDefinedValueTypeDefinition


class UserDefinedValueTypeDefinition(IrAbc):
    _ast_node: SolcUserDefinedValueTypeDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    __name: str
    __underlying_type: TypeNameAbc

    def __init__(
        self,
        init: IrInitTuple,
        user_defined_value_type_definition: SolcUserDefinedValueTypeDefinition,
        parent: IrAbc,
    ):
        super().__init__(init, user_defined_value_type_definition, parent)
        self.__name = user_defined_value_type_definition.name
        self.__underlying_type = TypeNameAbc.from_ast(
            init, user_defined_value_type_definition.underlying_type, self
        )

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        return self._parent

    @property
    def name(self) -> str:
        return self.__name

    @property
    def underlying_type(self) -> TypeNameAbc:
        return self.__underlying_type
