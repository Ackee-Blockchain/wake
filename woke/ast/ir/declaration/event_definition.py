from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Tuple, Union

from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcEventDefinition, SolcStructuredDocumentation


class EventDefinition(DeclarationAbc):
    """
    Definition of an event.
    !!! example
        ```solidity
        event Transfer(address indexed from, address indexed to, uint256 value);
        ```
    """
    _ast_node: SolcEventDefinition
    _parent: ContractDefinition

    __anonymous: bool
    __parameters: ParameterList
    __documentation: Optional[Union[StructuredDocumentation, str]]
    __event_selector: Optional[bytes]

    def __init__(
        self, init: IrInitTuple, event: SolcEventDefinition, parent: SolidityAbc
    ):
        super().__init__(init, event, parent)
        self.__anonymous = event.anonymous
        self.__parameters = ParameterList(init, event.parameters, self)

        if event.documentation is None:
            self.__documentation = None
        elif isinstance(event.documentation, SolcStructuredDocumentation):
            self.__documentation = StructuredDocumentation(
                init, event.documentation, self
            )
        elif isinstance(event.documentation, str):
            self.__documentation = event.documentation
        else:
            raise TypeError(
                f"Unknown type of documentation: {type(event.documentation)}"
            )
        self.__event_selector = (
            bytes.fromhex(event.event_selector) if event.event_selector else None
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__parameters
        if isinstance(self.__documentation, StructuredDocumentation):
            yield from self.__documentation

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
    @lru_cache(maxsize=None)
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
        return self.__anonymous

    @property
    def parameters(self) -> ParameterList:
        """
        Returns:
            Parameter list describing parameters of the event.
        """
        return self.__parameters

    @property
    def documentation(self) -> Optional[Union[StructuredDocumentation, str]]:
        """
        Of [StructuredDocumentation][woke.ast.ir.meta.structured_documentation.StructuredDocumentation] type since Solidity 0.6.3.
        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation string, if any.
        """
        return self.__documentation

    @property
    def event_selector(self) -> Optional[bytes]:
        """
        Available since Solidity 0.8.13.
        Returns:
            Selector of the event.
        """
        return self.__event_selector
