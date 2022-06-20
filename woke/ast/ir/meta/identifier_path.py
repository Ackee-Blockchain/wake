from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
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
