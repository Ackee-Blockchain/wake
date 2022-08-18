from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    YulAssignment,
    YulBlock,
    YulBreak,
    YulContinue,
    YulExpressionStatement,
    YulForLoop,
    YulFunctionDefinition,
    YulIf,
    YulLeave,
    YulSwitch,
    YulVariableDeclaration,
)

from .abc import YulAbc

if TYPE_CHECKING:
    from woke.ast.ir.statement.inline_assembly import InlineAssembly

    from .assignment import Assignment
    from .break_statement import Break
    from .case_statement import Case
    from .continue_statement import Continue
    from .expression_statement import ExpressionStatement
    from .for_loop import ForLoop
    from .function_definition import FunctionDefinition
    from .if_statement import If
    from .leave import Leave
    from .switch import Switch
    from .variable_declaration import VariableDeclaration


class Block(YulAbc):
    _parent: Union[InlineAssembly, Block, ForLoop, FunctionDefinition, If, Case]
    __statements: List[
        Union[
            Assignment,
            "Block",
            Break,
            Continue,
            ExpressionStatement,
            Leave,
            ForLoop,
            FunctionDefinition,
            If,
            Switch,
            VariableDeclaration,
        ]
    ]

    def __init__(
        self, init: IrInitTuple, block: YulBlock, parent: Union[InlineAssembly, YulAbc]
    ):
        from .assignment import Assignment
        from .break_statement import Break
        from .continue_statement import Continue
        from .expression_statement import ExpressionStatement
        from .for_loop import ForLoop
        from .function_definition import FunctionDefinition
        from .if_statement import If
        from .leave import Leave
        from .switch import Switch
        from .variable_declaration import VariableDeclaration

        super().__init__(init, block, parent)
        self.__statements = []
        for statement in block.statements:
            if isinstance(statement, YulAssignment):
                self.__statements.append(Assignment(init, statement, self))
            elif isinstance(statement, YulBlock):
                self.__statements.append(Block(init, statement, self))
            elif isinstance(statement, YulBreak):
                self.__statements.append(Break(init, statement, self))
            elif isinstance(statement, YulContinue):
                self.__statements.append(Continue(init, statement, self))
            elif isinstance(statement, YulExpressionStatement):
                self.__statements.append(ExpressionStatement(init, statement, self))
            elif isinstance(statement, YulLeave):
                self.__statements.append(Leave(init, statement, self))
            elif isinstance(statement, YulForLoop):
                self.__statements.append(ForLoop(init, statement, self))
            elif isinstance(statement, YulFunctionDefinition):
                self.__statements.append(FunctionDefinition(init, statement, self))
            elif isinstance(statement, YulIf):
                self.__statements.append(If(init, statement, self))
            elif isinstance(statement, YulSwitch):
                self.__statements.append(Switch(init, statement, self))
            elif isinstance(statement, YulVariableDeclaration):
                self.__statements.append(VariableDeclaration(init, statement, self))
            else:
                assert False, f"Unexpected type: {type(statement)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        for statement in self.__statements:
            yield from statement

    @property
    def parent(
        self,
    ) -> Union[InlineAssembly, Block, ForLoop, FunctionDefinition, If, Case]:
        return self._parent

    @property
    def statements(
        self,
    ) -> Tuple[
        Union[
            Assignment,
            "Block",
            Break,
            Continue,
            ExpressionStatement,
            Leave,
            ForLoop,
            FunctionDefinition,
            If,
            Switch,
            VariableDeclaration,
        ]
    ]:
        return tuple(self.__statements)
