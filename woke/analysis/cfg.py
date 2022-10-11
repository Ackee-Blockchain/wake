from __future__ import annotations

import enum
import logging
from typing import Dict, List, Optional, Tuple, Union

import networkx as nx

from woke.ast.enums import GlobalSymbolsEnum
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.block import Block
from woke.ast.ir.statement.break_statement import Break
from woke.ast.ir.statement.continue_statement import Continue
from woke.ast.ir.statement.do_while_statement import DoWhileStatement
from woke.ast.ir.statement.expression_statement import ExpressionStatement
from woke.ast.ir.statement.for_statement import ForStatement
from woke.ast.ir.statement.if_statement import IfStatement
from woke.ast.ir.statement.return_statement import Return
from woke.ast.ir.statement.revert_statement import RevertStatement
from woke.ast.ir.statement.try_statement import TryStatement
from woke.ast.ir.statement.unchecked_block import UncheckedBlock
from woke.ast.ir.statement.while_statement import WhileStatement

logger = logging.getLogger(__name__)


class TransitionCondition(str, enum.Enum):
    IS_TRUE = "is true"
    IS_FALSE = "is false"
    ALWAYS = "always"
    NEVER = "never"
    TRY_SUCCEEDED = "succeeded"
    TRY_REVERTED = "reverted"
    TRY_PANICKED = "panicked"
    TRY_FAILED = "failed"


class ControlFlowGraph:
    __graph: nx.DiGraph
    __declaration: Union[FunctionDefinition, ModifierDefinition]
    __statements_lookup: Dict[StatementAbc, CfgBlock]
    __start_block: CfgBlock
    __end_block: CfgBlock

    def __init__(self, declaration: Union[FunctionDefinition, ModifierDefinition]):
        if declaration.body is None:
            raise ValueError("Function body is None.")
        self.__declaration = declaration

        self.__graph = nx.DiGraph()
        self.__start_block = CfgBlock()
        self.__graph.add_node(self.__start_block)
        self.__end_block = CfgBlock()
        self.__graph.add_node(self.__end_block)

        last = CfgBlock.from_statement(
            self.__graph,
            self.__start_block,
            self.__end_block,
            None,
            None,
            declaration.body,
        )
        self.__graph.add_edge(
            last, self.__end_block, condition=(TransitionCondition.ALWAYS, None)
        )

        while _normalize(self.__graph, self.__start_block, self.__end_block):
            pass

        if (
            len(self.__end_block.statements) == 0
            and len(self.__graph.in_edges(self.__end_block)) == 1
        ):
            edge = next(iter(self.__graph.in_edges(self.__end_block, data=True)))
            if edge[2]["condition"][0] == TransitionCondition.ALWAYS:
                self.__graph.remove_node(self.__end_block)
                self.__end_block = edge[0]

        self.__statements_lookup = {
            stmt: block for block in self.__graph.nodes for stmt in block.statements
        }
        for node in self.__graph.nodes:
            for stmt in node.statements:
                self.__statements_lookup[stmt] = node
            if node.control_statement is not None:
                self.__statements_lookup[node.control_statement] = node

    @property
    def graph(self):
        return self.__graph.copy(as_view=True)

    @property
    def start_block(self) -> CfgBlock:
        return self.__start_block

    @property
    def end_block(self) -> CfgBlock:
        return self.__end_block

    def get_cfg_block(self, statement: StatementAbc) -> CfgBlock:
        return self.__statements_lookup[statement]

    def is_reachable(self, start: StatementAbc, end: StatementAbc) -> bool:
        start_block = self.__statements_lookup[start]
        end_block = self.__statements_lookup[end]
        if start_block == end_block:
            if end == end_block.control_statement:
                return True
            start_index = start_block.statements.index(start)
            end_index = end_block.statements.index(end)
            if start_index <= end_index:  # also EQUAL?
                return True
            try:
                nx.find_cycle(self.__graph, start_block)
                return True
            except nx.NetworkXNoCycle:
                return False
        else:
            return nx.has_path(self.__graph, start_block, end_block)


def _normalize(graph: nx.DiGraph, start: CfgBlock, end: CfgBlock) -> bool:
    changed = False
    to_be_removed = set()

    for node in graph.nodes:
        for out_edge in list(graph.out_edges(node, data=True)):
            if out_edge[2]["condition"][0] == TransitionCondition.NEVER:
                graph.remove_edge(out_edge[0], out_edge[1])
                changed = True

        if (
            len(node.statements) == 0
            and len(graph.out_edges(node)) == 1
            and node != start
        ):
            edge = next(iter(graph.out_edges(node, data=True)))
            if edge[2]["condition"][0] == TransitionCondition.ALWAYS:
                to = edge[1]
                in_edges = list(graph.in_edges(node, data=True))
                for from_, _, data in in_edges:
                    graph.add_edge(from_, to, condition=data["condition"])
                    graph.remove_edge(from_, node)
                to_be_removed.add(node)
                changed = True

        if (
            len(node.statements) == 0
            and len(graph.in_edges(node)) == 0
            and node not in {start, end}
        ):
            to_be_removed.add(node)
            changed = True
            for edge in list(graph.out_edges(node)):
                graph.remove_edge(edge[0], edge[1])

    for node in to_be_removed:
        graph.remove_node(node)

    return changed


class CfgBlock:
    __id_counter: int = 0
    __id: int
    __statements: List[StatementAbc]
    # control statement is always the last statement
    __control_statement: Optional[
        Union[DoWhileStatement, ForStatement, IfStatement, TryStatement, WhileStatement]
    ]

    def __init__(self):
        self.__id = self.__class__.__id_counter
        self.__class__.__id_counter += 1
        self.__statements = []
        self.__control_statement = None

    def __str__(self):
        return (
            "\n".join(statement.source for statement in self.statements)
            if len(self.statements) > 0
            else ""
        )

    @property
    def id(self) -> int:
        return self.__id

    @property
    def statements(self) -> Tuple[StatementAbc]:
        return tuple(self.__statements)

    @property
    def control_statement(
        self,
    ) -> Optional[
        Union[DoWhileStatement, ForStatement, IfStatement, TryStatement, WhileStatement]
    ]:
        return self.__control_statement

    @classmethod
    def from_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        function_end: CfgBlock,
        loop_body: Optional[CfgBlock],
        loop_body_next: Optional[CfgBlock],
        statement: StatementAbc,
    ) -> CfgBlock:
        if isinstance(statement, (Block, UncheckedBlock)):
            for body_statement in statement.statements:
                prev = cls.from_statement(
                    graph, prev, function_end, loop_body, loop_body_next, body_statement
                )
            return prev
        elif isinstance(statement, Break):
            prev.__statements.append(statement)
            next = CfgBlock()
            assert loop_body_next is not None
            graph.add_node(next)
            graph.add_edge(
                prev, loop_body_next, condition=(TransitionCondition.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionCondition.NEVER, None))
            return next
        elif isinstance(statement, Continue):
            prev.__statements.append(statement)
            next = CfgBlock()
            assert loop_body is not None
            graph.add_node(next)
            graph.add_edge(
                prev, loop_body, condition=(TransitionCondition.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionCondition.NEVER, None))
            return next
        elif isinstance(statement, DoWhileStatement):
            return cls.from_do_while_statement(graph, prev, function_end, statement)
        elif isinstance(statement, ForStatement):
            return cls.from_for_statement(graph, prev, function_end, statement)
        elif isinstance(statement, IfStatement):
            return cls.from_if_statement(
                graph, prev, function_end, loop_body, loop_body_next, statement
            )
        elif isinstance(statement, (Return, RevertStatement)):
            prev.__statements.append(statement)
            next = CfgBlock()
            graph.add_node(next)
            graph.add_edge(
                prev, function_end, condition=(TransitionCondition.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionCondition.NEVER, None))
            return next
        elif isinstance(statement, ExpressionStatement):
            expr = statement.expression
            if (
                isinstance(expr, FunctionCall)
                and expr.function_called == GlobalSymbolsEnum.REVERT
            ):
                prev.__statements.append(statement)
                next = CfgBlock()
                graph.add_node(next)
                graph.add_edge(
                    prev, function_end, condition=(TransitionCondition.ALWAYS, None)
                )
                graph.add_edge(prev, next, condition=(TransitionCondition.NEVER, None))
                return next
            else:
                prev.__statements.append(statement)
                return prev
        elif isinstance(statement, TryStatement):
            return cls.from_try_statement(
                graph, prev, function_end, loop_body, loop_body_next, statement
            )
        elif isinstance(statement, WhileStatement):
            return cls.from_while_statement(graph, prev, function_end, statement)
        else:
            prev.__statements.append(statement)
            return prev

    @classmethod
    def from_if_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        function_end: CfgBlock,
        loop_body: Optional[CfgBlock],
        loop_body_next: Optional[CfgBlock],
        if_statement: IfStatement,
    ) -> CfgBlock:
        assert prev.__control_statement is None
        prev.__control_statement = if_statement
        true_block = CfgBlock()
        graph.add_node(true_block)
        true_block_end = cls.from_statement(
            graph,
            true_block,
            function_end,
            loop_body,
            loop_body_next,
            if_statement.true_body,
        )

        false_block = CfgBlock()
        graph.add_node(false_block)

        if if_statement.false_body is None:
            false_block_end = false_block
        else:
            false_block_end = cls.from_statement(
                graph,
                false_block,
                function_end,
                loop_body,
                loop_body_next,
                if_statement.false_body,
            )

        next = CfgBlock()
        graph.add_node(next)
        graph.add_edge(
            prev,
            true_block,
            condition=(TransitionCondition.IS_TRUE, if_statement.condition),
        )
        graph.add_edge(
            prev,
            false_block,
            condition=(TransitionCondition.IS_FALSE, if_statement.condition),
        )
        graph.add_edge(
            true_block_end, next, condition=(TransitionCondition.ALWAYS, None)
        )
        graph.add_edge(
            false_block_end, next, condition=(TransitionCondition.ALWAYS, None)
        )
        return next

    @classmethod
    def from_do_while_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        function_end: CfgBlock,
        do_while_statement: DoWhileStatement,
    ) -> CfgBlock:
        body = CfgBlock()
        graph.add_node(body)
        next = CfgBlock()
        graph.add_node(next)
        body_end = cls.from_statement(
            graph, body, function_end, body, next, do_while_statement.body
        )
        assert body_end.__control_statement is None
        body_end.__control_statement = do_while_statement

        graph.add_edge(prev, body, condition=(TransitionCondition.ALWAYS, None))
        graph.add_edge(
            body_end,
            next,
            condition=(TransitionCondition.IS_FALSE, do_while_statement.condition),
        )
        graph.add_edge(
            body_end,
            body,
            condition=(TransitionCondition.IS_TRUE, do_while_statement.condition),
        )
        return next

    @classmethod
    def from_for_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        function_end: CfgBlock,
        for_statement: ForStatement,
    ) -> CfgBlock:
        if for_statement.initialization_expression is not None:
            prev.__statements.append(for_statement.initialization_expression)
        assert prev.__control_statement is None
        prev.__control_statement = for_statement

        body = CfgBlock()
        graph.add_node(body)
        next = CfgBlock()
        graph.add_node(next)
        body_end = CfgBlock()
        graph.add_node(body_end)
        tmp = cls.from_statement(
            graph, body, function_end, body_end, next, for_statement.body
        )

        if tmp == body:
            body_end = tmp
            if for_statement.loop_expression is not None:
                body_end.__statements.append(for_statement.loop_expression)
        else:
            body_end.__statements = list(tmp.__statements)

            for start, _, data in graph.in_edges(tmp, data=True):
                graph.add_edge(start, body_end, condition=data["condition"])

            for end, _, data in graph.out_edges(tmp, data=True):
                graph.add_edge(body_end, end, condition=data["condition"])

            graph.remove_node(tmp)
            if for_statement.loop_expression is not None:
                body_end.__statements.append(for_statement.loop_expression)

        graph.add_edge(
            prev, body, condition=(TransitionCondition.IS_TRUE, for_statement.condition)
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionCondition.IS_FALSE, for_statement.condition),
        )
        graph.add_edge(
            body_end,
            body,
            condition=(TransitionCondition.IS_TRUE, for_statement.condition),
        )
        graph.add_edge(
            body_end,
            next,
            condition=(TransitionCondition.IS_FALSE, for_statement.condition),
        )
        return next

    @classmethod
    def from_try_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        function_end: CfgBlock,
        loop_body: Optional[CfgBlock],
        loop_body_next: Optional[CfgBlock],
        try_statement: TryStatement,
    ) -> CfgBlock:
        assert prev.__control_statement is None
        prev.__control_statement = try_statement

        success_block = CfgBlock()
        graph.add_node(success_block)
        success_block_end = cls.from_statement(
            graph,
            success_block,
            function_end,
            loop_body,
            loop_body_next,
            try_statement.clauses[0].block,
        )

        revert_block = None
        revert_block_end = None
        panic_block = None
        panic_block_end = None
        fail_block = None
        fail_block_end = None
        for clause in try_statement.clauses[1:]:
            if clause.error_name == "Error":
                revert_block = CfgBlock()
                graph.add_node(revert_block)
                revert_block_end = cls.from_statement(
                    graph,
                    revert_block,
                    function_end,
                    loop_body,
                    loop_body_next,
                    clause.block,
                )
            elif clause.error_name == "Panic":
                panic_block = CfgBlock()
                graph.add_node(panic_block)
                panic_block_end = cls.from_statement(
                    graph,
                    panic_block,
                    function_end,
                    loop_body,
                    loop_body_next,
                    clause.block,
                )
            elif clause.error_name == "":
                fail_block = CfgBlock()
                graph.add_node(fail_block)
                fail_block_end = cls.from_statement(
                    graph,
                    fail_block,
                    function_end,
                    loop_body,
                    loop_body_next,
                    clause.block,
                )
            else:
                raise NotImplementedError(f"Unknown error name: {clause.error_name}")

        next = CfgBlock()
        graph.add_node(next)

        graph.add_edge(
            prev,
            success_block,
            condition=(TransitionCondition.TRY_SUCCEEDED, try_statement.external_call),
        )
        graph.add_edge(
            success_block_end, next, condition=(TransitionCondition.ALWAYS, None)
        )
        if revert_block is not None:
            graph.add_edge(
                prev,
                revert_block,
                condition=(
                    TransitionCondition.TRY_REVERTED,
                    try_statement.external_call,
                ),
            )
            graph.add_edge(
                revert_block_end, next, condition=(TransitionCondition.ALWAYS, None)
            )
        if panic_block is not None:
            graph.add_edge(
                prev,
                panic_block,
                condition=(
                    TransitionCondition.TRY_PANICKED,
                    try_statement.external_call,
                ),
            )
            graph.add_edge(
                panic_block_end, next, condition=(TransitionCondition.ALWAYS, None)
            )
        if fail_block is not None:
            graph.add_edge(
                prev,
                fail_block,
                condition=(TransitionCondition.TRY_FAILED, try_statement.external_call),
            )
            graph.add_edge(
                fail_block_end, next, condition=(TransitionCondition.ALWAYS, None)
            )
        return next

    @classmethod
    def from_while_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        function_end: CfgBlock,
        while_statement: WhileStatement,
    ) -> CfgBlock:
        assert prev.__control_statement is None
        prev.__control_statement = while_statement

        body = CfgBlock()
        graph.add_node(body)
        next = CfgBlock()
        graph.add_node(next)
        body_end = cls.from_statement(
            graph, body, function_end, body, next, while_statement.body
        )

        graph.add_edge(
            prev,
            body,
            condition=(TransitionCondition.IS_TRUE, while_statement.condition),
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionCondition.IS_FALSE, while_statement.condition),
        )
        graph.add_edge(
            body_end,
            body,
            condition=(TransitionCondition.IS_TRUE, while_statement.condition),
        )
        graph.add_edge(
            body_end,
            next,
            condition=(TransitionCondition.IS_FALSE, while_statement.condition),
        )
        return next
