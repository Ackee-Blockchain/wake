from __future__ import annotations

import weakref
from functools import lru_cache
from typing import TYPE_CHECKING, FrozenSet, Iterator, Optional, Set, Tuple, Union

from Crypto.Hash import keccak

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcErrorDefinition
from wake.ir.utils import IrInitTuple
from wake.utils.decorators import weak_self_lru_cache

from ..abc import is_not_none
from ..meta.parameter_list import ParameterList
from ..meta.structured_documentation import StructuredDocumentation
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from ..expressions.identifier import Identifier
    from ..expressions.member_access import MemberAccess
    from ..meta.source_unit import SourceUnit
    from .contract_definition import ContractDefinition


class ErrorDefinition(DeclarationAbc):
    """
    Definition of an error.

    !!! example
        ```solidity
        error InsufficientBalance(uint256 available, uint256 required);
        ```
    """

    _ast_node: SolcErrorDefinition
    _parent: weakref.ReferenceType[Union[ContractDefinition, SourceUnit]]

    _parameters: ParameterList
    _documentation: Optional[StructuredDocumentation]
    _error_selector: Optional[bytes]

    # not a part of the AST
    _used_in: Set[weakref.ReferenceType[ContractDefinition]]

    def __init__(
        self, init: IrInitTuple, error: SolcErrorDefinition, parent: SolidityAbc
    ):
        super().__init__(init, error, parent)
        self._parameters = ParameterList(init, error.parameters, self)
        self._documentation = (
            StructuredDocumentation(init, error.documentation, self)
            if error.documentation is not None
            else None
        )
        self._error_selector = (
            bytes.fromhex(error.error_selector) if error.error_selector else None
        )
        self._used_in = set()

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._parameters
        if self._documentation is not None:
            yield from self._documentation

    def __setstate__(self, state):
        super().__setstate__(state)
        self._used_in = set()

    @classmethod
    def _strip_weakrefs(cls, state: dict):
        super()._strip_weakrefs(state)
        del state["_used_in"]

    def _parse_name_location(self) -> Tuple[int, int]:
        # SolcErrorDefinition node always contains name_location attribute
        # this method is implemented here just for completeness and to satisfy the linter
        byte_start = self._ast_node.name_location.byte_offset
        byte_length = self._ast_node.name_location.byte_length
        return byte_start, byte_start + byte_length

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        """
        Returns:
            Parent IR node.
        """
        return super().parent

    @property
    def children(self) -> Iterator[Union[ParameterList, StructuredDocumentation]]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._parameters
        if self._documentation is not None:
            yield self._documentation

    @property
    @weak_self_lru_cache(maxsize=2048)
    def canonical_name(self) -> str:
        from .contract_definition import ContractDefinition

        if isinstance(self.parent, ContractDefinition):
            return f"{self.parent.canonical_name}.{self._name}"
        return self._name

    @property
    @weak_self_lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        ret = (
            f"error {self._name}("
            + ", ".join(
                param.declaration_string for param in self.parameters.parameters
            )
            + ")"
        )
        if self.documentation is not None:
            return (
                "/// "
                + "\n///".join(line for line in self.documentation.text.splitlines())
                + "\n"
                + ret
            )
        return ret

    @property
    def parameters(self) -> ParameterList:
        """
        Returns:
            Parameter list describing parameters of the error.
        """
        return self._parameters

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        """
        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation string, if any.
        """
        return self._documentation

    @property
    @weak_self_lru_cache(maxsize=2048)
    def error_selector(self) -> bytes:
        """
        Returns:
            Selector of the error.
        """
        if self._error_selector is not None:
            return self._error_selector
        else:
            signature = f"{self._name}("
            signature += ",".join(
                param.type.abi_type for param in self.parameters.parameters
            )
            signature += ")"
            h = keccak.new(data=signature.encode("utf-8"), digest_bits=256)
            return h.digest()[:4]

    @property
    def used_in(self) -> FrozenSet[ContractDefinition]:
        """
        Returns:
            Contracts (including child contracts) that use this error in a revert statement, a contract that defines this error and contracts that inherit this error.
        """
        return frozenset(is_not_none(c()) for c in self._used_in)

    @property
    def references(
        self,
    ) -> FrozenSet[Union[Identifier, MemberAccess,]]:
        """
        Returns:
            Set of all IR nodes referencing this error.
        """
        from ..expressions.identifier import Identifier
        from ..expressions.member_access import MemberAccess

        refs = [is_not_none(r()) for r in self._references]

        try:
            ref = next(
                ref for ref in refs if not isinstance(ref, (Identifier, MemberAccess))
            )
            raise AssertionError(f"Unexpected reference type: {ref}")
        except StopIteration:
            return frozenset(refs)  # pyright: ignore reportGeneralTypeIssues
