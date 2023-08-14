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
    from woke.ir.declaration.function_definition import FunctionDefinition
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
    _referenced_declaration_ids: Set[AstNodeId]

    def __init__(
        self, init: IrInitTuple, identifier: SolcIdentifier, parent: SolidityAbc
    ):
        from ..meta.import_directive import ImportDirective

        super().__init__(init, identifier, parent)
        self._name = identifier.name
        self._overloaded_declarations = list(identifier.overloaded_declarations)
        if identifier.referenced_declaration is None:
            assert isinstance(self._parent, ImportDirective)
            self._referenced_declaration_ids = set()
        else:
            self._referenced_declaration_ids = {identifier.referenced_declaration}
        init.reference_resolver.register_post_process_callback(
            self._post_process, priority=-1
        )

    def _post_process(self, callback_params: CallbackParams):
        from ..meta.import_directive import ImportDirective

        new_referenced_declaration_ids = set()

        for referenced_declaration_id in self._referenced_declaration_ids:
            if referenced_declaration_id < 0:
                global_symbol = GlobalSymbolsEnum(referenced_declaration_id)
                self._reference_resolver.register_global_symbol_reference(
                    global_symbol, self
                )
                self._reference_resolver.register_destroy_callback(
                    self.file, partial(self._destroy, global_symbol)
                )
                new_referenced_declaration_ids.add(referenced_declaration_id)
            else:
                node = self._reference_resolver.resolve_node(
                    referenced_declaration_id, self._cu_hash
                )

                if isinstance(node, DeclarationAbc):
                    node.register_reference(self)
                    self._reference_resolver.register_destroy_callback(
                        self.file, partial(self._destroy, node)
                    )
                    new_referenced_declaration_ids.add(referenced_declaration_id)
                elif isinstance(node, ImportDirective):
                    # make this node to reference the source unit directly
                    assert node.unit_alias is not None
                    source_unit = callback_params.source_units[node.imported_file]
                    node_path_order = self._reference_resolver.get_node_path_order(
                        AstNodeId(source_unit.ast_node_id),
                        source_unit.cu_hash,
                    )
                    new_referenced_declaration_ids.add(
                        self._reference_resolver.get_ast_id_from_cu_node_path_order(
                            node_path_order, self.cu_hash
                        )
                    )
                else:
                    raise TypeError(f"Unexpected type: {type(node)}")

        self._referenced_declaration_ids = new_referenced_declaration_ids

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
    ) -> Union[DeclarationAbc, GlobalSymbolsEnum, SourceUnit, Set[FunctionDefinition]]:
        def resolve(referenced_declaration_id: AstNodeId):
            if referenced_declaration_id < 0:
                return GlobalSymbolsEnum(referenced_declaration_id)

            node = self._reference_resolver.resolve_node(
                referenced_declaration_id, self._cu_hash
            )
            assert isinstance(
                node, (DeclarationAbc, SourceUnit)
            ), f"Unexpected type: {type(node)}\n{node.source}\n{self.source}\n{self.file}"
            return node

        from ..declaration.function_definition import FunctionDefinition
        from ..meta.source_unit import SourceUnit

        assert len(self._referenced_declaration_ids) != 0
        if len(self._referenced_declaration_ids) == 1:
            return resolve(next(iter(self._referenced_declaration_ids)))
        else:
            # Identifier in ImportDirective symbol alias referencing multiple overloaded functions
            ret = set(map(resolve, self._referenced_declaration_ids))
            assert all(isinstance(x, FunctionDefinition) for x in ret)
            return ret  # pyright: ignore reportGeneralTypeIssues

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
