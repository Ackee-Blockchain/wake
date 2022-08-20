from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcVariableDeclarationStatement

if TYPE_CHECKING:
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class VariableDeclarationStatement(StatementAbc):
    _ast_node: SolcVariableDeclarationStatement
    _parent: Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]

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
    def parent(
        self,
    ) -> Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
    ]:
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
    def initial_value(self) -> Optional[ExpressionAbc]:
        return self.__initial_value

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> ModifiesStateFlag:
        ret = ModifiesStateFlag(0)
        if self.initial_value is not None:
            ret |= self.initial_value.modifies_state
            if any(
                declaration.is_state_variable
                for declaration in self.declarations
                if declaration is not None
            ):
                ret |= ModifiesStateFlag.MODIFIES_STATE_VAR
        return ret
