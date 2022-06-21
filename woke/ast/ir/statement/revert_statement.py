from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcRevertStatement


class RevertStatement(StatementAbc):
    _ast_node: SolcRevertStatement
    _parent: IrAbc  # TODO: make this more specific

    __error_call: FunctionCall
    __documentation: Optional[str]

    def __init__(self, init: IrInitTuple, revert: SolcRevertStatement, parent: IrAbc):
        super().__init__(init, revert, parent)
        self.__error_call = FunctionCall(init, revert.error_call, self)
        self.__documentation = revert.documentation

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def error_call(self) -> FunctionCall:
        return self.__error_call

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
