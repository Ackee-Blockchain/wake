from typing import Iterator, List, Optional, Tuple

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcVariableDeclarationStatement


class VariableDeclarationStatement(StatementAbc):
    _ast_node: SolcVariableDeclarationStatement
    _parent: SolidityAbc  # TODO: make this more specific

    __assignments: List[Optional[AstNodeId]]
    __declarations: List[Optional[VariableDeclaration]]
    __documentation: Optional[str]
    __initial_value: Optional[ExpressionAbc]

    def __init__(
        self,
        init: IrInitTuple,
        variable_declaration_statement: SolcVariableDeclarationStatement,
        parent: SolidityAbc,
    ):
        super().__init__(init, variable_declaration_statement, parent)
        # TODO assignments are just AST IDs of the variable declarations ?
        self.__assignments = list(variable_declaration_statement.assignments)

        self.__declarations = []
        for declaration in variable_declaration_statement.declarations:
            if declaration is None:
                self.__declarations.append(None)
            else:
                self.__declarations.append(VariableDeclaration(init, declaration, self))

        self.__documentation = variable_declaration_statement.documentation
        if variable_declaration_statement.initial_value is None:
            self.__initial_value = None
        else:
            self.__initial_value = ExpressionAbc.from_ast(
                init, variable_declaration_statement.initial_value, self
            )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        for declaration in self.__declarations:
            if declaration is not None:
                yield from declaration
        if self.__initial_value is not None:
            yield from self.__initial_value

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def declarations(self) -> Tuple[Optional[VariableDeclaration]]:
        return tuple(self.__declarations)

    @property
    def assignments(self) -> Tuple[Optional[VariableDeclaration]]:
        ret = []
        for assignment in self.__assignments:
            if assignment is None:
                ret.append(None)
            else:
                node = self._reference_resolver.resolve_node(assignment, self.cu_hash)
                assert isinstance(node, VariableDeclaration)
                ret.append(node)
        return tuple(ret)

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    def initial_values(self) -> Optional[ExpressionAbc]:
        return self.__initial_value
