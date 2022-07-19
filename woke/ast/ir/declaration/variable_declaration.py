from __future__ import annotations

import logging
import re
from functools import lru_cache, partial
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

from woke.ast.enums import Mutability, StorageLocation, Visibility
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.type_name.abc import TypeNameAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcVariableDeclaration

from ..meta.override_specifier import OverrideSpecifier
from ..reference_resolver import CallbackParams

if TYPE_CHECKING:
    from ..declaration.contract_definition import ContractDefinition
    from ..declaration.function_definition import FunctionDefinition
    from ..declaration.struct_definition import StructDefinition
    from ..meta.parameter_list import ParameterList
    from ..meta.source_unit import SourceUnit
    from ..statement.variable_declaration_statement import VariableDeclarationStatement


logger = logging.getLogger(__name__)


class VariableDeclaration(DeclarationAbc):
    _ast_node: SolcVariableDeclaration
    _parent: Union[
        ContractDefinition,
        ParameterList,
        SourceUnit,
        StructDefinition,
        VariableDeclarationStatement,
    ]

    __constant: bool
    # __scope
    __mutability: Optional[Mutability]
    __state_variable: bool
    __storage_location: StorageLocation
    __visibility: Visibility
    __base_functions: Optional[List[AstNodeId]]
    __documentation: Optional[StructuredDocumentation]
    __function_selector: Optional[bytes]
    __indexed: bool
    __overrides: Optional[OverrideSpecifier]
    __type_name: TypeNameAbc
    __value: Optional[ExpressionAbc]

    def __init__(
        self,
        init: IrInitTuple,
        variable_declaration: SolcVariableDeclaration,
        parent: IrAbc,
    ):
        super().__init__(init, variable_declaration, parent)
        self.__constant = variable_declaration.constant
        self.__mutability = variable_declaration.mutability
        # TODO scope
        self.__state_variable = variable_declaration.state_variable
        self.__storage_location = variable_declaration.storage_location
        # TODO type descriptions?
        self.__visibility = variable_declaration.visibility
        self.__base_functions = (
            list(variable_declaration.base_functions)
            if variable_declaration.base_functions
            else None
        )
        self.__documentation = (
            StructuredDocumentation(init, variable_declaration.documentation, self)
            if variable_declaration.documentation
            else None
        )
        self.__function_selector = (
            bytes.fromhex(variable_declaration.function_selector)
            if variable_declaration.function_selector
            else None
        )
        # TODO function selector?
        self.__indexed = variable_declaration.indexed or False
        self.__overrides = (
            OverrideSpecifier(init, variable_declaration.overrides, self)
            if variable_declaration.overrides
            else None
        )

        # type name should not be None
        # prior 0.5.0, there was a `var` keyword which resulted in the type name being None
        assert (
            variable_declaration.type_name is not None
        ), "Variable declaration must have a type name"
        self.__type_name = TypeNameAbc.from_ast(
            init, variable_declaration.type_name, self
        )
        self.__value = (
            ExpressionAbc.from_ast(init, variable_declaration.value, self)
            if variable_declaration.value is not None
            else None
        )
        self._reference_resolver.register_post_process_callback(self.__post_process)

    def __post_process(self, callback_params: CallbackParams):
        if self.base_functions is not None:
            base_functions = self.base_functions
            for base_function in base_functions:
                base_function._child_functions.add(self)
            self._reference_resolver.register_destroy_callback(
                self.file, partial(self.__destroy, base_functions)
            )

    def __destroy(self, base_functions: Tuple[FunctionDefinition]) -> None:
        for base_function in base_functions:
            base_function._child_functions.discard(self)

    def _parse_name_location(self) -> Tuple[int, int]:
        # this one is a bit tricky
        # it is easier to parse the variable declaration from the end (while omitting an optional assigned expression)
        if self.__value is None:
            source_without_value = self._source
        else:
            length_without_value = self.__value.byte_location[0] - self.byte_location[0]
            source_without_value = self._source[:length_without_value]

        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        VARIABLE_RE = re.compile(
            r"(?P<name>{identifier})(\s*=)?\s*$".format(identifier=IDENTIFIER).encode(
                "utf-8"
            )
        )
        match = VARIABLE_RE.search(source_without_value)
        assert match
        byte_start = self._ast_node.src.byte_offset
        return byte_start + match.start("name"), byte_start + match.end("name")

    @property
    def parent(
        self,
    ) -> Union[
        ContractDefinition,
        ParameterList,
        SourceUnit,
        StructDefinition,
        VariableDeclarationStatement,
    ]:
        return self._parent

    @property
    @lru_cache(maxsize=None)
    def canonical_name(self) -> str:
        node = self.parent
        while not isinstance(node, DeclarationAbc):
            if node is None:
                assert (
                    False
                ), "Variable declaration must have a parent of type DeclarationAbc"
            node = node.parent
        return f"{node.canonical_name}.{self.name}"

    @property
    def constant(self) -> bool:
        return self.__constant

    @property
    def mutability(self) -> Mutability:
        if self.__mutability is None:
            relative_type_end = (
                self.__type_name.byte_location[1] - self.byte_location[0]
            )
            relative_name_start = self.name_location[0] - self.byte_location[0]
            keywords_source = self._source[relative_type_end:relative_name_start]

            if b"immutable" in keywords_source:
                self.__mutability = Mutability.IMMUTABLE
            elif self.__constant:
                self.__mutability = Mutability.CONSTANT
            else:
                self.__mutability = Mutability.MUTABLE
        return self.__mutability

    @property
    def is_state_variable(self) -> bool:
        return self.__state_variable

    @property
    def storage_location(self) -> StorageLocation:
        return self.__storage_location

    @property
    def visibility(self) -> Visibility:
        return self.__visibility

    @property
    def base_functions(self) -> Optional[Tuple[FunctionDefinition]]:
        from ..declaration.function_definition import FunctionDefinition

        if self.__base_functions is None:
            return None
        base_functions = []
        for base_function_id in self.__base_functions:
            base_function = self._reference_resolver.resolve_node(
                base_function_id, self._cu_hash
            )
            assert isinstance(base_function, FunctionDefinition)
            base_functions.append(base_function)
        return tuple(base_functions)

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation

    @property
    def function_selector(self) -> Optional[bytes]:
        return self.__function_selector

    @property
    def indexed(self) -> bool:
        return self.__indexed

    @property
    def overrides(self) -> Optional[OverrideSpecifier]:
        return self.__overrides

    @property
    def type_name(self) -> TypeNameAbc:
        return self.__type_name

    @property
    def value(self) -> Optional[ExpressionAbc]:
        return self.__value
