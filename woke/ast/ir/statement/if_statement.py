from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcIfStatement


class IfStatement(StatementAbc):
    _ast_node: SolcIfStatement
    _parent: IrAbc  # TODO: make this more specific

    __condition: ExpressionAbc
    __true_body: StatementAbc
    __documentation: Optional[str]
    __false_body: Optional[StatementAbc]

    def __init__(self, init: IrInitTuple, if_statement: SolcIfStatement, parent: IrAbc):
        super().__init__(init, if_statement, parent)
        self.__condition = ExpressionAbc.from_ast(init, if_statement.condition, self)
        self.__true_body = StatementAbc.from_ast(init, if_statement.true_body, self)
        self.__false_body = (
            None
            if if_statement.false_body is None
            else StatementAbc.from_ast(init, if_statement.false_body, self)
        )
        self.__documentation = if_statement.documentation

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def condition(self) -> ExpressionAbc:
        return self.__condition

    @property
    def true_body(self) -> StatementAbc:
        return self.__true_body

    @property
    def false_body(self) -> Optional[StatementAbc]:
        return self.__false_body

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
