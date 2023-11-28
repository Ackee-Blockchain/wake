from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING, FrozenSet, Iterator, Optional, Set, Tuple, Union

from Crypto.Hash import keccak

from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition
    from ..expressions.identifier import Identifier
    from ..expressions.member_access import MemberAccess
    from ..meta.source_unit import SourceUnit

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcEventDefinition, SolcStructuredDocumentation
from wake.ir.meta.parameter_list import ParameterList
from wake.ir.meta.structured_documentation import StructuredDocumentation
from wake.ir.utils import IrInitTuple


class EventDefinition(DeclarationAbc):
    """
    Definition of an event.
    !!! example
        ```solidity
        event Transfer(address indexed from, address indexed to, uint256 value);
        ```
    """

    _ast_node: SolcEventDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    _anonymous: bool
    _parameters: ParameterList
    _documentation: Optional[Union[StructuredDocumentation, str]]
    _event_selector: Optional[bytes]

    # not a part of the AST
    _used_in: Set[ContractDefinition]

    def __init__(
        self, init: IrInitTuple, event: SolcEventDefinition, parent: SolidityAbc
    ):
        super().__init__(init, event, parent)
        self._anonymous = event.anonymous
        self._parameters = ParameterList(init, event.parameters, self)

        if event.documentation is None:
            self._documentation = None
        elif isinstance(event.documentation, SolcStructuredDocumentation):
            self._documentation = StructuredDocumentation(
                init, event.documentation, self
            )
        elif isinstance(event.documentation, str):
            self._documentation = event.documentation
        else:
            raise TypeError(
                f"Unknown type of documentation: {type(event.documentation)}"
            )
        self._event_selector = (
            bytes.fromhex(event.event_selector) if event.event_selector else None
        )
        self._used_in = set()

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._parameters
        if isinstance(self._documentation, StructuredDocumentation):
            yield from self._documentation

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        EVENT_RE = re.compile(
            r"^\s*event\s+(?P<name>{identifier})".format(identifier=IDENTIFIER).encode(
                "utf-8"
            )
        )

        byte_start = self._ast_node.src.byte_offset
        match = EVENT_RE.match(self._source)
        assert match
        return byte_start + match.start("name"), byte_start + match.end("name")

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def canonical_name(self) -> str:
        from .contract_definition import ContractDefinition

        if isinstance(self._parent, ContractDefinition):
            return f"{self._parent.canonical_name}.{self._name}"
        return self._name

    @property
    @lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        ret = (
            f"event {self._name}("
            + ", ".join(
                param.declaration_string for param in self.parameters.parameters
            )
            + f"){' anonymous' if self.anonymous else ''}"
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
    def anonymous(self) -> bool:
        """
        !!! example
            ```solidity
            event Transfer(address indexed from, address indexed to, uint256 value) anonymous;
            ```

        Returns:
            `True` if the event is anonymous, `False` otherwise.
        """
        return self._anonymous

    @property
    def parameters(self) -> ParameterList:
        """
        Returns:
            Parameter list describing parameters of the event.
        """
        return self._parameters

    @property
    def documentation(self) -> Optional[Union[StructuredDocumentation, str]]:
        """
        Of [StructuredDocumentation][wake.ir.meta.structured_documentation.StructuredDocumentation] type since Solidity 0.6.3.

        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation string, if any.
        """
        return self._documentation

    @property
    @lru_cache(maxsize=2048)
    def event_selector(self) -> bytes:
        """
        Returns:
            Selector of the event.
        """
        if self._event_selector is not None:
            return self._event_selector
        else:
            signature = f"{self._name}({','.join(param.type.abi_type for param in self.parameters.parameters)})"
            h = keccak.new(data=signature.encode("utf-8"), digest_bits=256)
            return h.digest()

    @property
    def used_in(self) -> FrozenSet[ContractDefinition]:
        """
        Returns:
            Contracts (including child contracts) that emit this event, a contract that defines this event and contracts that inherit this event.
        """
        return frozenset(self._used_in)

    @property
    def references(
        self,
    ) -> FrozenSet[Union[Identifier, MemberAccess,]]:
        """
        Returns:
            Set of all IR nodes referencing this event.
        """
        from ..expressions.identifier import Identifier
        from ..expressions.member_access import MemberAccess

        try:
            ref = next(
                ref
                for ref in self._references
                if not isinstance(ref, (Identifier, MemberAccess))
            )
            raise AssertionError(f"Unexpected reference type: {ref}")
        except StopIteration:
            return frozenset(
                self._references
            )  # pyright: ignore reportGeneralTypeIssues
