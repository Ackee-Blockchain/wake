from typing import Optional

from woke.ast.ir.abc import IrAbc, TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcUserDefinedTypeName


class UserDefinedTypeName(TypeNameAbc):
    _ast_node: SolcUserDefinedTypeName
    _parent: IrAbc  # TODO: make this more specific

    # __referenced_declaration
    # __contract_scope
    __name: Optional[str]
    # __path_node

    def __init__(
        self,
        init: IrInitTuple,
        user_defined_type_name: SolcUserDefinedTypeName,
        parent: IrAbc,
    ):
        super().__init__(init, user_defined_type_name, parent)
        self.__name = user_defined_type_name.name

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def name(self) -> Optional[str]:
        return self.__name
