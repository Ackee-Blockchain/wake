from __future__ import annotations

from functools import lru_cache, partial
from typing import TYPE_CHECKING, FrozenSet, List, Set, Tuple, Union

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import AstNodeId, SolcIdentifier
from wake.ir.declarations.abc import DeclarationAbc
from wake.ir.declarations.variable_declaration import VariableDeclaration
from wake.ir.enums import GlobalSymbol, ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.reference_resolver import CallbackParams
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..declarations.function_definition import FunctionDefinition
    from ..meta.import_directive import ImportDirective
    from ..meta.source_unit import SourceUnit
    from ..statements.abc import StatementAbc
    from ..yul.abc import YulAbc


class Identifier(ExpressionAbc):
    """
    Represents a single identifier referencing a declaration (or multiple overloaded declarations).
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
                global_symbol = GlobalSymbol(referenced_declaration_id)
                self._reference_resolver.register_global_symbol_reference(
                    global_symbol, self
                )
                self._reference_resolver.register_destroy_callback(
                    self.source_unit.file, partial(self._destroy, global_symbol)
                )
                new_referenced_declaration_ids.add(referenced_declaration_id)
            else:
                node = self._reference_resolver.resolve_node(
                    referenced_declaration_id, self.source_unit.cu_hash
                )

                if isinstance(node, DeclarationAbc):
                    node.register_reference(self)
                    self._reference_resolver.register_destroy_callback(
                        self.source_unit.file, partial(self._destroy, node)
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
                            node_path_order, self.source_unit.cu_hash
                        )
                    )
                else:
                    raise TypeError(f"Unexpected type: {type(node)}")

        self._referenced_declaration_ids = new_referenced_declaration_ids

    def _destroy(
        self, referenced_declaration: Union[GlobalSymbol, DeclarationAbc]
    ) -> None:
        if isinstance(referenced_declaration, GlobalSymbol):
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
        """
        Returns:
            Name of the referenced declaration.
        """
        return self._name

    @property
    def overloaded_declarations(self) -> FrozenSet[FunctionDefinition]:
        """
        Returns:
            Empty set if [referenced_declaration][wake.ir.expressions.identifier.Identifier.referenced_declaration] is not overloaded.
                Otherwise, set of all overloaded declarations (including [referenced_declaration][wake.ir.expressions.identifier.Identifier.referenced_declaration]) with the same name as the identifier.
        """
        from ..declarations.function_definition import FunctionDefinition

        overloaded_declarations = set()
        for overloaded_declaration_id in self._overloaded_declarations:
            assert overloaded_declaration_id >= 0

            overloaded_declaration = self._reference_resolver.resolve_node(
                overloaded_declaration_id, self.source_unit.cu_hash
            )
            assert isinstance(overloaded_declaration, FunctionDefinition)
            overloaded_declarations.add(overloaded_declaration)

        # fix overloaded declarations are not set for identifiers in ImportDirective symbol alias
        if len(overloaded_declarations) == 0:
            ref_decl = self.referenced_declaration
            if isinstance(ref_decl, set):
                return frozenset(ref_decl)

        return frozenset(overloaded_declarations)

    @property
    def referenced_declaration(
        self,
    ) -> Union[DeclarationAbc, GlobalSymbol, SourceUnit, FrozenSet[FunctionDefinition]]:
        """
        If the referenced function name is overloaded and a single function cannot be inferred from the context, returns a set of all overloaded functions.
        This is the case of identifiers in [ImportDirectives][wake.ir.meta.import_directive.ImportDirective].
        In the following example, the identifier `max` in the example import directive references both `max` functions from `Math.sol`:

        ```solidity title="Math.sol"
        function max(uint256 a, uint256 b) pure returns (uint256) {
            return a >= b ? a : b;
        }
        function max(int256 a, int256 b) pure returns (int256) {
            return a >= b ? a : b;
        }
        ```

        ```solidity title="A.sol"
        import { max } from "./Math.sol";
        ```

        If the referenced function name is overloaded and a single function can be inferred from the context, returns the inferred function.

        A [SourceUnit][wake.ir.meta.source_unit.SourceUnit] is returned if the identifier references a source unit alias defined in an [ImportDirective][wake.ir.meta.import_directive.ImportDirective].
        For example, `Math` in `Math.max(-1, 2)` references the source unit `Math.sol`:

        ```solidity
        import "./Math.sol" as Math;

        contract C {
            function test() public {
                Math.max(-1, 2);
            }
        }
        ```

        Returns:
            Referenced declaration(s).
        """

        def resolve(referenced_declaration_id: AstNodeId):
            if referenced_declaration_id < 0:
                return GlobalSymbol(referenced_declaration_id)

            node = self._reference_resolver.resolve_node(
                referenced_declaration_id, self.source_unit.cu_hash
            )
            assert isinstance(
                node, (DeclarationAbc, SourceUnit)
            ), f"Unexpected type: {type(node)}\n{node.source}\n{self.source}\n{self.source_unit.file}"
            return node

        from ..declarations.function_definition import FunctionDefinition
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
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return set()
