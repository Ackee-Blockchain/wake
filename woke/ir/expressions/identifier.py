from __future__ import annotations

from functools import lru_cache, partial
from typing import TYPE_CHECKING, List, Optional, Set, Tuple, Union

from woke.ir.abc import IrAbc, SolidityAbc
from woke.ir.ast import AstNodeId, SolcIdentifier
from woke.ir.declarations.abc import DeclarationAbc
from woke.ir.declarations.variable_declaration import VariableDeclaration
from woke.ir.enums import GlobalSymbolsEnum, ModifiesStateFlag
from woke.ir.expressions.abc import ExpressionAbc
from woke.ir.reference_resolver import CallbackParams
from woke.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from woke.ir.meta.import_directive import ImportDirective
    from woke.ir.meta.source_unit import SourceUnit


class Identifier(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcIdentifier
    _parent: SolidityAbc  # TODO: make this more specific

    _name: str
    _overloaded_declarations: List[AstNodeId]
    _referenced_declaration_id: Optional[AstNodeId]

    def __init__(
        self, init: IrInitTuple, identifier: SolcIdentifier, parent: SolidityAbc
    ):
        from ..meta.import_directive import ImportDirective

        super().__init__(init, identifier, parent)
        self._name = identifier.name
        self._overloaded_declarations = list(identifier.overloaded_declarations)
        self._referenced_declaration_id = identifier.referenced_declaration
        if self._referenced_declaration_id is None:
            assert isinstance(self._parent, ImportDirective)
        init.reference_resolver.register_post_process_callback(
            self._post_process, priority=-1
        )

    def _post_process(self, callback_params: CallbackParams):
        from ..meta.import_directive import ImportDirective

        assert self._referenced_declaration_id is not None
        if self._referenced_declaration_id < 0:
            global_symbol = GlobalSymbolsEnum(self._referenced_declaration_id)
            self._reference_resolver.register_global_symbol_reference(
                global_symbol, self
            )
            self._reference_resolver.register_destroy_callback(
                self.file, partial(self._destroy, global_symbol)
            )
        else:
            node = self._reference_resolver.resolve_node(
                self._referenced_declaration_id, self._cu_hash
            )

            if isinstance(node, DeclarationAbc):
                node.register_reference(self)
                self._reference_resolver.register_destroy_callback(
                    self.file, partial(self._destroy, node)
                )
            elif isinstance(node, ImportDirective):
                # make this node to reference the source unit directly
                assert node.unit_alias is not None
                source_unit = callback_params.source_units[node.imported_file]
                node_path_order = self._reference_resolver.get_node_path_order(
                    AstNodeId(source_unit.ast_node_id),
                    source_unit.cu_hash,
                )
                self._referenced_declaration_id = (
                    self._reference_resolver.get_ast_id_from_cu_node_path_order(
                        node_path_order, self.cu_hash
                    )
                )
            else:
                raise TypeError(f"Unexpected type: {type(node)}")

    def _destroy(
        self, referenced_declaration: Union[GlobalSymbolsEnum, DeclarationAbc]
    ) -> None:
        if isinstance(referenced_declaration, GlobalSymbolsEnum):
            self._reference_resolver.unregister_global_symbol_reference(
                referenced_declaration, self
            )
        elif isinstance(referenced_declaration, DeclarationAbc):
            referenced_declaration.unregister_reference(self)
        else:
            raise TypeError(f"Unexpected type: {type(referenced_declaration)}")

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def name(self) -> str:
        return self._name

    @property
    def overloaded_declarations(self) -> Tuple[DeclarationAbc, ...]:
        overloaded_declarations = []
        for overloaded_declaration_id in self._overloaded_declarations:
            if overloaded_declaration_id < 0:
                continue

            overloaded_declaration = self._reference_resolver.resolve_node(
                overloaded_declaration_id, self._cu_hash
            )
            assert isinstance(overloaded_declaration, DeclarationAbc)
            overloaded_declarations.append(overloaded_declaration)
        return tuple(overloaded_declarations)

    @property
    def referenced_declaration(
        self,
    ) -> Union[DeclarationAbc, GlobalSymbolsEnum, SourceUnit]:
        from ..meta.source_unit import SourceUnit

        assert self._referenced_declaration_id is not None
        if self._referenced_declaration_id < 0:
            return GlobalSymbolsEnum(self._referenced_declaration_id)

        node = self._reference_resolver.resolve_node(
            self._referenced_declaration_id, self._cu_hash
        )
        assert isinstance(
            node, (DeclarationAbc, SourceUnit)
        ), f"Unexpected type: {type(node)}\n{node.source}\n{self.source}\n{self.file}"
        return node

    @property
    @lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        referenced_declaration = self.referenced_declaration
        return (
            isinstance(referenced_declaration, VariableDeclaration)
            and referenced_declaration.is_state_variable
        )

    @property
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return set()
