from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcIdentifierPath


class IdentifierPath(IrAbc):
    _ast_node: SolcIdentifierPath
    _parent: IrAbc  # TODO: make this more specific

    __name: str
    # __referenced_declaration

    def __init__(
        self, init: IrInitTuple, identifier_path: SolcIdentifierPath, parent: IrAbc
    ):
        super().__init__(init, identifier_path, parent)
        self.__name = identifier_path.name

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def name(self) -> str:
        return self.__name
