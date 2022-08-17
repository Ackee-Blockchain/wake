from typing import Iterator, Optional

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcEmitStatement


class EmitStatement(StatementAbc):
    _ast_node: SolcEmitStatement
    _parent: SolidityAbc

    __event_call: FunctionCall
    __documentation: Optional[str]

    def __init__(self, init: IrInitTuple, emit: SolcEmitStatement, parent: SolidityAbc):
        super().__init__(init, emit, parent)
        self.__event_call = FunctionCall(init, emit.event_call, self)
        self.__documentation = emit.documentation

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__event_call

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def event_call(self) -> FunctionCall:
        return self.__event_call

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
