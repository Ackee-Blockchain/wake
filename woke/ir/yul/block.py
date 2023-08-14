from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, List, Tuple, Union

from woke.ir.ast import (
    SolcYulAssignment,
    SolcYulBlock,
    SolcYulBreak,
    SolcYulContinue,
    SolcYulExpressionStatement,
    SolcYulForLoop,
    SolcYulFunctionDefinition,
    SolcYulIf,
    SolcYulLeave,
    SolcYulSwitch,
    SolcYulVariableDeclaration,
)
from woke.ir.utils import IrInitTuple

from .abc import YulAbc, YulStatementAbc

if TYPE_CHECKING:
    from woke.ir.statements.inline_assembly import InlineAssembly

    from .assignment import YulAssignment
    from .break_statement import YulBreak
    from .case_statement import YulCase
    from .continue_statement import YulContinue
    from .expression_statement import YulExpressionStatement
    from .for_loop import YulForLoop
    from .function_definition import YulFunctionDefinition
    from .if_statement import YulIf
    from .leave import YulLeave
    from .switch import YulSwitch
    from .variable_declaration import YulVariableDeclaration


class YulBlock(YulStatementAbc):
    """
    TBD
    """

    _parent: Union[
        InlineAssembly, YulBlock, YulForLoop, YulFunctionDefinition, YulIf, YulCase
    ]
    _statements: List[
        Union[
            YulAssignment,
            "YulBlock",
            YulBreak,
            YulContinue,
            YulExpressionStatement,
            YulLeave,
            YulForLoop,
            YulFunctionDefinition,
            YulIf,
            YulSwitch,
            YulVariableDeclaration,
        ]
    ]

    def __init__(
        self,
        init: IrInitTuple,
        block: SolcYulBlock,
        parent: Union[InlineAssembly, YulAbc],
    ):
        from .assignment import YulAssignment
        from .break_statement import YulBreak
        from .continue_statement import YulContinue
        from .expression_statement import YulExpressionStatement
        from .for_loop import YulForLoop
        from .function_definition import YulFunctionDefinition
        from .if_statement import YulIf
        from .leave import YulLeave
        from .switch import YulSwitch
        from .variable_declaration import YulVariableDeclaration

        super().__init__(init, block, parent)
        self._statements = []
        for statement in block.statements:
            if isinstance(statement, SolcYulAssignment):
                self._statements.append(YulAssignment(init, statement, self))
            elif isinstance(statement, SolcYulBlock):
                self._statements.append(YulBlock(init, statement, self))
            elif isinstance(statement, SolcYulBreak):
                self._statements.append(YulBreak(init, statement, self))
            elif isinstance(statement, SolcYulContinue):
                self._statements.append(YulContinue(init, statement, self))
            elif isinstance(statement, SolcYulExpressionStatement):
                self._statements.append(YulExpressionStatement(init, statement, self))
            elif isinstance(statement, SolcYulLeave):
                self._statements.append(YulLeave(init, statement, self))
            elif isinstance(statement, SolcYulForLoop):
                self._statements.append(YulForLoop(init, statement, self))
            elif isinstance(statement, SolcYulFunctionDefinition):
                self._statements.append(YulFunctionDefinition(init, statement, self))
            elif isinstance(statement, SolcYulIf):
                self._statements.append(YulIf(init, statement, self))
            elif isinstance(statement, SolcYulSwitch):
                self._statements.append(YulSwitch(init, statement, self))
            elif isinstance(statement, SolcYulVariableDeclaration):
                self._statements.append(YulVariableDeclaration(init, statement, self))
            else:
                assert False, f"Unexpected type: {type(statement)}"

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        for statement in self._statements:
            yield from statement

    @property
    def parent(
        self,
    ) -> Union[
        InlineAssembly, YulBlock, YulForLoop, YulFunctionDefinition, YulIf, YulCase
    ]:
        return self._parent

    @property
    def statements(
        self,
    ) -> Tuple[
        Union[
            YulAssignment,
            "YulBlock",
            YulBreak,
            YulContinue,
            YulExpressionStatement,
            YulLeave,
            YulForLoop,
            YulFunctionDefinition,
            YulIf,
            YulSwitch,
            YulVariableDeclaration,
        ],
        ...,
    ]:
        return tuple(self._statements)
