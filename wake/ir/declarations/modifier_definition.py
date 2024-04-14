from __future__ import annotations

import re
from bisect import bisect
from collections import deque
from functools import lru_cache, partial
from typing import (
    TYPE_CHECKING,
    Deque,
    FrozenSet,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from ...regex_parser import SoliditySourceParser
from ..meta.override_specifier import OverrideSpecifier
from ..reference_resolver import CallbackParams
from ..statements.block import Block
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from wake.analysis.cfg import ControlFlowGraph
    from .contract_definition import ContractDefinition
    from ..expressions.identifier import Identifier
    from ..expressions.member_access import MemberAccess
    from ..meta.identifier_path import IdentifierPathPart
    from ..statements.inline_assembly import ExternalReference
    from ..expressions.unary_operation import UnaryOperation
    from ..expressions.binary_operation import BinaryOperation

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import AstNodeId, SolcModifierDefinition, SolcStructuredDocumentation
from wake.ir.enums import Visibility
from wake.ir.meta.parameter_list import ParameterList
from wake.ir.meta.structured_documentation import StructuredDocumentation
from wake.ir.utils import IrInitTuple


class ModifierDefinition(DeclarationAbc):
    """
    Definition of a modifier.

    !!! example
        ```solidity
        modifier onlyOwner {
            require(msg.sender == owner);
            _;
        }
        ```
    """

    _ast_node: SolcModifierDefinition
    _parent: ContractDefinition
    _child_modifiers: Set[ModifierDefinition]

    _body: Optional[Block]
    _implemented: bool
    _parameters: ParameterList
    _virtual: bool
    _visibility: Visibility
    _base_modifiers: List[AstNodeId]
    _documentation: Optional[Union[StructuredDocumentation, str]]
    _overrides: Optional[OverrideSpecifier]

    def __init__(
        self, init: IrInitTuple, modifier: SolcModifierDefinition, parent: SolidityAbc
    ):
        super().__init__(init, modifier, parent)
        self._child_modifiers = set()

        self._body = Block(init, modifier.body, self) if modifier.body else None
        self._implemented = self._body is not None
        self._parameters = ParameterList(init, modifier.parameters, self)
        self._virtual = modifier.virtual
        self._visibility = modifier.visibility
        self._base_modifiers = (
            list(modifier.base_modifiers) if modifier.base_modifiers is not None else []
        )
        if modifier.documentation is None:
            self._documentation = None
        elif isinstance(modifier.documentation, SolcStructuredDocumentation):
            self._documentation = StructuredDocumentation(
                init, modifier.documentation, self
            )
        elif isinstance(modifier.documentation, str):
            self._documentation = modifier.documentation
        else:
            raise TypeError(
                f"Unknown type of documentation: {type(modifier.documentation)}"
            )
        self._overrides = (
            OverrideSpecifier(init, modifier.overrides, self)
            if modifier.overrides is not None
            else None
        )
        self._reference_resolver.register_post_process_callback(self._post_process)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        if self._body is not None:
            yield from self._body
        yield from self._parameters
        if isinstance(self._documentation, StructuredDocumentation):
            yield from self._documentation
        if self._overrides is not None:
            yield from self._overrides

    def _post_process(self, callback_params: CallbackParams):
        base_modifiers = self.base_modifiers
        for base_modifier in base_modifiers:
            base_modifier._child_modifiers.add(self)
        self._reference_resolver.register_destroy_callback(
            self.source_unit.file, partial(self._destroy, base_modifiers)
        )

    def _destroy(self, base_modifiers: Tuple[ModifierDefinition, ...]) -> None:
        for base_modifier in base_modifiers:
            base_modifier._child_modifiers.remove(self)

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        MODIFIER_RE = re.compile(
            r"^\s*modifier\s+(?P<name>{identifier})".format(
                identifier=IDENTIFIER
            ).encode("utf-8")
        )

        source = bytearray(self._source)
        _, stripped_sums = SoliditySourceParser.strip_comments(source)

        byte_start = self._ast_node.src.byte_offset
        match = MODIFIER_RE.match(source)
        assert match

        if len(stripped_sums) == 0:
            stripped = 0
        else:
            index = bisect([s[0] for s in stripped_sums], match.start("name"))
            if index == 0:
                stripped = 0
            else:
                stripped = stripped_sums[index - 1][1]

        return (
            byte_start + match.start("name") + stripped,
            byte_start + match.end("name") + stripped,
        )

    def get_all_references(
        self, include_declarations: bool
    ) -> Iterator[
        Union[
            DeclarationAbc,
            Identifier,
            IdentifierPathPart,
            MemberAccess,
            ExternalReference,
            UnaryOperation,
            BinaryOperation,
        ]
    ]:
        processed_declarations: Set[ModifierDefinition] = {self}
        declarations_queue: Deque[ModifierDefinition] = deque([self])

        while declarations_queue:
            declaration = declarations_queue.pop()
            if include_declarations:
                yield declaration
            yield from declaration.references

            for base_modifier in declaration.base_modifiers:
                if base_modifier not in processed_declarations:
                    declarations_queue.append(base_modifier)
                    processed_declarations.add(base_modifier)
            for child_modifier in declaration.child_modifiers:
                if child_modifier not in processed_declarations:
                    declarations_queue.append(child_modifier)
                    processed_declarations.add(child_modifier)

    @property
    def parent(self) -> ContractDefinition:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def canonical_name(self) -> str:
        return f"{self._parent.canonical_name}.{self._name}"

    @property
    @lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        ret = f"modifier {self._name}"
        ret += (
            f"({', '.join(param.declaration_string for param in self.parameters.parameters)})"
            if len(self.parameters.parameters) > 0
            else ""
        )
        ret += " virtual" if self.virtual else ""
        ret += (
            (
                f" override"
                + (
                    "("
                    + ", ".join(
                        override.source for override in self.overrides.overrides
                    )
                    + ")"
                    if len(self.overrides.overrides) > 0
                    else ""
                )
            )
            if self.overrides is not None
            else ""
        )

        if isinstance(self.documentation, StructuredDocumentation):
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.text.splitlines())
                + "\n"
                + ret
            )
        elif isinstance(self.documentation, str):
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.splitlines())
                + "\n"
                + ret
            )
        else:
            return ret

    @property
    def body(self) -> Optional[Block]:
        """
        Returns:
            Body of the modifier, if any.
        """
        return self._body

    @property
    def implemented(self) -> bool:
        """
        Returns:
            `True` if the modifier [body][wake.ir.declarations.modifier_definition.ModifierDefinition.body] is not `None`, `False` otherwise.
        """
        return self._implemented

    @property
    def parameters(self) -> ParameterList:
        """
        Returns:
            Parameter list describing the modifier parameters.
        """
        return self._parameters

    @property
    def virtual(self) -> bool:
        """
        Returns:
            `True` if the modifier is virtual, `False` otherwise.
        """
        return self._virtual

    @property
    def visibility(self) -> Visibility:
        """
        Returns:
            Visibility of the modifier.
        """
        return self._visibility

    @property
    def base_modifiers(self) -> Tuple[ModifierDefinition, ...]:
        """
        !!! example
            `B.mod` on lines 6-8 lists `A.mod` on line 2 as a base modifier.

            `C.mod` on lines 12-14 lists only `B.mod` on lines 6-8 as a base modifier.
            ```solidity linenums="1"
            abstract contract A {
                modifier mod virtual;
            }

            contract B is A {
                modifier mod virtual override {
                    _;
                }
            }

            contract C is B {
                modifier mod override {
                    _;
                }
            }
            ```

        !!! example
            `B1.mod` on lines 6-8 lists `A.mod` on line 2 as a base modifier.

            `B2.mod` on lines 12-14 lists `A.mod` on line 2 as a base modifier.

            `C.mod` on lines 18-20 lists `B1.mod` on lines 6-8 and `B2.mod` on lines 12-14 as base modifiers.
            ```solidity linenums="1"
            abstract contract A {
                modifier mod virtual;
            }

            contract B1 is A {
                modifier mod virtual override {
                    _;
                }
            }

            contract B2 is A {
                modifier mod virtual override {
                    _;
                }
            }

            contract C is B1, B2 {
                modifier mod override(B1, B2) {
                    _;
                }
            }
            ```

        Returns:
            List of base modifiers overridden by this modifier.
        """
        base_modifiers = []
        for base_modifier_id in self._base_modifiers:
            base_modifier = self._reference_resolver.resolve_node(
                base_modifier_id, self.source_unit.cu_hash
            )
            assert isinstance(base_modifier, ModifierDefinition)
            base_modifiers.append(base_modifier)
        return tuple(base_modifiers)

    @property
    def child_modifiers(self) -> FrozenSet[ModifierDefinition]:
        """
        Returns:
            Modifiers that list this modifier in their [base_modifiers][wake.ir.declarations.modifier_definition.ModifierDefinition.base_modifiers] property.
        """
        return frozenset(self._child_modifiers)

    @property
    def documentation(self) -> Optional[Union[StructuredDocumentation, str]]:
        """
        Of [StructuredDocumentation][wake.ir.meta.structured_documentation.StructuredDocumentation] type since Solidity 0.6.3.

        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation string, if any.
        """
        return self._documentation

    @property
    def overrides(self) -> Optional[OverrideSpecifier]:
        """
        Returns override specifier as present in the source code.
        !!! example
            `A.mod` on line 2 does not have an override specifier.

            `B1.mod` on lines 6-8 has an override specifier with the [overrides][wake.ir.meta.override_specifier.OverrideSpecifier.overrides] property empty.

            `B2.mod` on lines 12-14 has an override specifier with the [overrides][wake.ir.meta.override_specifier.OverrideSpecifier.overrides] property empty.

            `C.mod` on lines 18-20 has an override specifier with the [overrides][wake.ir.meta.override_specifier.OverrideSpecifier.overrides] property containg two items referencing the contracts `B1` and `B2` ([ContractDefinition][wake.ir.declarations.contract_definition.ContractDefinition]).
            ```solidity linenums="1"
            abstract contract A {
                modifier mod virtual;
            }

            contract B1 is A {
                modifier mod virtual override {
                    _;
                }
            }

            contract B2 is A {
                modifier mod virtual override {
                    _;
                }
            }

            contract C is B1, B2 {
                modifier mod override(B1, B2) {
                    _;
                }
            }
            ```

        Returns:
            Override specifier, if any.
        """
        return self._overrides

    @property
    @lru_cache(maxsize=128)
    def cfg(self) -> ControlFlowGraph:
        """
        Raises:
            ValueError: If the modifier is not implemented.

        Returns:
            Control flow graph of the modifier.
        """
        from wake.analysis.cfg import ControlFlowGraph

        if not self._implemented:
            raise ValueError("Cannot create CFG for unimplemented modifier")

        return ControlFlowGraph(self)

    @property
    def references(
        self,
    ) -> FrozenSet[Union[Identifier, IdentifierPathPart]]:
        """
        Until Solidity 0.8.0, modifiers were referenced in [ModifierInvocations][wake.ir.meta.modifier_invocation.ModifierInvocation]
        using [Identifiers][wake.ir.expressions.identifier.Identifier]. Version 0.8.0 started using [IdentifierPaths][wake.ir.meta.identifier_path.IdentifierPath] instead.

        Returns:
            Set of all IR nodes referencing this modifier.
        """
        from ..expressions.identifier import Identifier
        from ..meta.identifier_path import IdentifierPathPart

        try:
            ref = next(
                ref
                for ref in self._references
                if not isinstance(ref, (Identifier, IdentifierPathPart))
            )
            raise AssertionError(f"Unexpected reference type: {ref}")
        except StopIteration:
            return frozenset(
                self._references
            )  # pyright: ignore reportGeneralTypeIssues
