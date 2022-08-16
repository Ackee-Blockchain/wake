from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Tuple, Union

from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcEventDefinition, SolcStructuredDocumentation


class EventDefinition(DeclarationAbc):
    _ast_node: SolcEventDefinition
    _parent: ContractDefinition

    __anonymous: bool
    __parameters: ParameterList
    __documentation: Optional[Union[StructuredDocumentation, str]]

    def __init__(self, init: IrInitTuple, event: SolcEventDefinition, parent: IrAbc):
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
        # TODO event selector?

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
        return self.__anonymous

    @property
    def parameters(self) -> ParameterList:
        return self.__parameters

    @property
    def documentation(self) -> Optional[Union[StructuredDocumentation, str]]:
        return self.__documentation
