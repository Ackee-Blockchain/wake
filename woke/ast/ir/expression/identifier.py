from typing import List, Optional, Tuple

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcIdentifier


class Identifier(ExpressionAbc):
    _ast_node: SolcIdentifier
    _parent: IrAbc  # TODO: make this more specific

    __name: str
    __overloaded_declarations: List[AstNodeId]
    __referenced_declaration: Optional[AstNodeId]

    def __init__(self, init: IrInitTuple, identifier: SolcIdentifier, parent: IrAbc):
        super().__init__(init, identifier, parent)
        self.__name = identifier.name
        self.__overloaded_declarations = list(identifier.overloaded_declarations)
        self.__referenced_declaration = identifier.referenced_declaration

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def name(self) -> str:
        return self.__name

    @property
    def overloaded_declarations(self) -> Tuple[IrAbc]:
        return tuple(
            self._reference_resolver.resolve_node(node_id, self._cu_hash)
            for node_id in self.__overloaded_declarations
        )

    @property
    def referenced_declaration(self) -> Optional[DeclarationAbc]:
        if self.__referenced_declaration is None:
            return None
        node = self._reference_resolver.resolve_node(
            self.__referenced_declaration, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node
