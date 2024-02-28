from __future__ import annotations

from functools import reduce
from operator import or_
from typing import TYPE_CHECKING, Iterator, List, Set, Tuple, Union

from wake.ir.ast import (
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
from wake.ir.utils import IrInitTuple

from ..enums import ModifiesStateFlag
from .abc import YulAbc, YulStatementAbc

if TYPE_CHECKING:
    from wake.ir.statements.inline_assembly import InlineAssembly

    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
    from .assignment import YulAssignment
    from .break_statement import YulBreak
    from .case_ import YulCase
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
    Block statements group multiple statements into a single block.
    """

    _parent: Union[
        InlineAssembly, YulBlock, YulForLoop, YulFunctionDefinition, YulIf, YulCase
    ]
    _statements: List[YulStatementAbc]

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
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def statements(
        self,
    ) -> Tuple[YulStatementAbc, ...]:
        """
        Returns:
            Statements contained in this block.
        """
        return tuple(self._statements)

    @property
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return reduce(
            or_,
            (statement.modifies_state for statement in self.statements),
            set(),
        )
