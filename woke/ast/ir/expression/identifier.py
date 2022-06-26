from typing import List, Optional, Tuple

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.reference_resolver import CallbackParams
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcIdentifier


class Identifier(ExpressionAbc):
    _ast_node: SolcIdentifier
    _parent: IrAbc  # TODO: make this more specific

    __name: str
    __overloaded_declarations: List[AstNodeId]
    _referenced_declaration_id: Optional[AstNodeId]

    def __init__(self, init: IrInitTuple, identifier: SolcIdentifier, parent: IrAbc):
        super().__init__(init, identifier, parent)
        self.__name = identifier.name
        self.__overloaded_declarations = list(identifier.overloaded_declarations)
        self._referenced_declaration_id = identifier.referenced_declaration
        init.reference_resolver.register_post_process_callback(self.__post_process)

    def __post_process(self, callback_params: CallbackParams):
        referenced_declaration = self.referenced_declaration
        if referenced_declaration is not None:
            referenced_declaration.register_reference(self)

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def name(self) -> str:
        return self.__name

    @property
    def overloaded_declarations(self) -> Tuple[DeclarationAbc]:
        overloaded_declarations = []
        for overloaded_declaration_id in self.__overloaded_declarations:
            if overloaded_declaration_id < 0:
                continue

            overloaded_declaration = self._reference_resolver.resolve_node(
                overloaded_declaration_id, self._cu_hash
            )
            assert isinstance(overloaded_declaration, DeclarationAbc)
            overloaded_declarations.append(overloaded_declaration)
        return tuple(overloaded_declarations)

    @property
    def referenced_declaration(self) -> Optional[DeclarationAbc]:
        if (
            self._referenced_declaration_id is None
            or self._referenced_declaration_id < 0
        ):
            return None
        node = self._reference_resolver.resolve_node(
            self._referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
        return node
