from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcExpressionStatement


class ExpressionStatement(StatementAbc):
    _ast_node: SolcExpressionStatement
    _parent: IrAbc  # TODO: make this more specific

    __expression: ExpressionAbc
    __documentation: Optional[str]

    def __init__(
        self,
        init: IrInitTuple,
        expression_statement: SolcExpressionStatement,
        parent: IrAbc,
    ):
        super().__init__(init, expression_statement, parent)
        self.__expression = ExpressionAbc.from_ast(
            init, expression_statement.expression, self
        )
        self.__documentation = expression_statement.documentation

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def expression(self) -> ExpressionAbc:
        return self.__expression

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
