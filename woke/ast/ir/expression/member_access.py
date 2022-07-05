from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.declaration.enum_definition import EnumDefinition
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.reference_resolver import CallbackParams
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcMemberAccess


class MemberAccess(ExpressionAbc):
    _ast_node: SolcMemberAccess
    _parent: IrAbc  # TODO: make this more specific

    __expression: ExpressionAbc
    __member_name: str
    __referenced_declaration_id: Optional[AstNodeId]

    def __init__(
        self, init: IrInitTuple, member_access: SolcMemberAccess, parent: IrAbc
    ):
        super().__init__(init, member_access, parent)
        self.__expression = ExpressionAbc.from_ast(init, member_access.expression, self)
        self.__member_name = member_access.member_name
        self.__referenced_declaration_id = member_access.referenced_declaration

        self._reference_resolver.register_post_process_callback(self.__post_process)
        self._reference_resolver.register_destroy_callback(self.file, self.__destroy)

    def __post_process(self, callback_params: CallbackParams):
        # workaround for enum value bug in Solidity versions prior to 0.8.2
        if (
            isinstance(self.__expression, Identifier)
            and self.__referenced_declaration_id is None
            and self.__expression._referenced_declaration_id is not None
            and self.__expression._referenced_declaration_id >= 0
        ):
            referenced_declaration = self._reference_resolver.resolve_node(
                self.__expression._referenced_declaration_id, self.__expression.cu_hash
            )
            if isinstance(referenced_declaration, EnumDefinition):
                for enum_value in referenced_declaration.values:
                    if enum_value.name == self.__member_name:
                        node_path_order = self._reference_resolver.get_node_path_order(
                            AstNodeId(enum_value.ast_node_id), enum_value.cu_hash
                        )
                        this_cu_id = (
                            self._reference_resolver.get_ast_id_from_cu_node_path_order(
                                node_path_order, self.cu_hash
                            )
                        )
                        self.__referenced_declaration_id = this_cu_id
                        break

        referenced_declaration = self.referenced_declaration
        if referenced_declaration is not None:
            referenced_declaration.register_reference(self)

    def __destroy(self) -> None:
        referenced_declaration = self.referenced_declaration
        if referenced_declaration is not None:
            referenced_declaration.unregister_reference(self)

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def expression(self) -> ExpressionAbc:
        return self.__expression

    @property
    def member_name(self) -> str:
        return self.__member_name

    @property
    def referenced_declaration(self) -> Optional[DeclarationAbc]:
        if (
            self.__referenced_declaration_id is None
            or self.__referenced_declaration_id < 0
        ):
            return None
        node = self._reference_resolver.resolve_node(
            self.__referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node
