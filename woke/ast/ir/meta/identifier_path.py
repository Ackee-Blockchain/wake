from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.reference_resolver import CallbackParams
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcIdentifierPath


class IdentifierPath(IrAbc):
    _ast_node: SolcIdentifierPath
    _parent: IrAbc  # TODO: make this more specific

    __name: str
    __referenced_declaration_id: AstNodeId

    def __init__(
        self, init: IrInitTuple, identifier_path: SolcIdentifierPath, parent: IrAbc
    ):
        super().__init__(init, identifier_path, parent)
        self.__name = identifier_path.name
        self.__referenced_declaration_id = identifier_path.referenced_declaration
        assert self.__referenced_declaration_id >= 0
        self._reference_resolver.register_post_process_callback(self.__post_process)
        self._reference_resolver.register_destroy_callback(self.file, self.__destroy)

    def __post_process(self, callback_params: CallbackParams):
        self.referenced_declaration.register_reference(self)

    def __destroy(self) -> None:
        self.referenced_declaration.unregister_reference(self)

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def name(self) -> str:
        return self.__name

    @property
    def referenced_declaration(self) -> DeclarationAbc:
        node = self._reference_resolver.resolve_node(
            self.__referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node
