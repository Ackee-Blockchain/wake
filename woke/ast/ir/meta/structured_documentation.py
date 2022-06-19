from __future__ import annotations

from typing import TYPE_CHECKING, Union

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcStructuredDocumentation

# if TYPE_CHECKING:
# from .contract_definition import ContractDefinition
# from .error_definition import ErrorDefinition
# from .event_definition import EventDefinition
# from .function_definition import FunctionDefinition
# from .modifier_definition import ModifierDefinition
# from .variable_declaration import VariableDeclaration



class StructuredDocumentation(IrAbc):
    _ast_node: SolcStructuredDocumentation
    # _parent: Union[ContractDefinition, ErrorDefinition, EventDefinition, FunctionDefinition, ModifierDefinition, VariableDeclaration]

    __text: str

    def __init__(
        self,
        init: IrInitTuple,
        structured_documentation: SolcStructuredDocumentation,
        parent: IrAbc,
    ):
        super().__init__(init, structured_documentation, parent)
        self.__text = structured_documentation.text

    # @property
    # def parent(self) -> Union[ContractDefinition, ErrorDefinition, EventDefinition, FunctionDefinition, ModifierDefinition, VariableDeclaration]:
    # return self._parent

    @property
    def text(self) -> str:
        return self.__text
