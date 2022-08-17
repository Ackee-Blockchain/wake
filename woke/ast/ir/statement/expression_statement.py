from typing import Iterator, Optional

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcExpressionStatement


class ExpressionStatement(StatementAbc):
    _ast_node: SolcExpressionStatement
    _parent: SolidityAbc  # TODO: make this more specific

    __expression: ExpressionAbc
    __documentation: Optional[str]

    def __init__(
        self,
        init: IrInitTuple,
        expression_statement: SolcExpressionStatement,
        parent: SolidityAbc,
    ):
        super().__init__(init, expression_statement, parent)
        self.__expression = ExpressionAbc.from_ast(
            init, expression_statement.expression, self
        )
        self.__documentation = expression_statement.documentation

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__expression

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def expression(self) -> ExpressionAbc:
        return self.__expression

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
