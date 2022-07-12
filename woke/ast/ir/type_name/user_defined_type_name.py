from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Optional

from woke.ast.ir.reference_resolver import CallbackParams

if TYPE_CHECKING:
    from woke.ast.ir.declaration.contract_definition import ContractDefinition

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.meta.identifier_path import IdentifierPath
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcUserDefinedTypeName


class UserDefinedTypeName(TypeNameAbc):
    _ast_node: SolcUserDefinedTypeName
    _parent: IrAbc  # TODO: make this more specific

    __referenced_declaration_id: AstNodeId
    __contract_scope_id: Optional[AstNodeId]
    __name: Optional[str]
    __path_node: Optional[IdentifierPath]

    def __init__(
        self,
        init: IrInitTuple,
        user_defined_type_name: SolcUserDefinedTypeName,
        parent: IrAbc,
    ):
        super().__init__(init, user_defined_type_name, parent)
        self.__name = user_defined_type_name.name
        self.__referenced_declaration_id = user_defined_type_name.referenced_declaration
        assert self.__referenced_declaration_id >= 0
        self.__contract_scope_id = user_defined_type_name.contract_scope
        if user_defined_type_name.path_node is None:
            self.__path_node = None
        else:
            self.__path_node = IdentifierPath(
                init, user_defined_type_name.path_node, self
            )
        self._reference_resolver.register_post_process_callback(self.__post_process)

    def __post_process(self, callback_params: CallbackParams):
        if self.path_node is not None:
            assert self.referenced_declaration == self.path_node.referenced_declaration
        else:
            referenced_declaration = self.referenced_declaration
            referenced_declaration.register_reference(self)
            self._reference_resolver.register_destroy_callback(
                self.file, partial(self.__destroy, referenced_declaration)
            )

    def __destroy(self, referenced_declaration: DeclarationAbc) -> None:
        referenced_declaration.unregister_reference(self)

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def name(self) -> Optional[str]:
        return self.__name

    @property
    def referenced_declaration(self) -> DeclarationAbc:
        node = self._reference_resolver.resolve_node(
            self.__referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node

    @property
    def contract_scope(self) -> Optional[ContractDefinition]:
        if self.__contract_scope_id is None:
            return None
        node = self._reference_resolver.resolve_node(
            self.__contract_scope_id, self._cu_hash
        )
        assert isinstance(node, ContractDefinition)
        return node

    @property
    def path_node(self) -> Optional[IdentifierPath]:
        return self.__path_node
