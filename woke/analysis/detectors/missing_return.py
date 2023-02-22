from typing import List, Set

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.analysis.detectors.utils import check_all_return_params_set
from woke.ast.enums import GlobalSymbolsEnum
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.statement.expression_statement import ExpressionStatement
from woke.ast.ir.statement.inline_assembly import InlineAssembly
from woke.ast.ir.statement.return_statement import Return
from woke.ast.ir.statement.revert_statement import RevertStatement
from woke.ast.ir.yul.expression_statement import (
    ExpressionStatement as YulExpressionStatement,
)
from woke.ast.ir.yul.function_call import FunctionCall as YulFunctionCall


def check_missing_return(node: FunctionDefinition) -> List[DetectorResult]:
    cfg = node.cfg
    assert cfg is not None
    end = cfg.end_block
    graph = cfg.graph
    detections = []

    for block in graph.predecessors(end):
        has_return = False
        for stmt in block.statements:
            if isinstance(stmt, ExpressionStatement):
                if (
                    isinstance(stmt.expression, FunctionCall)
                    and stmt.expression.function_called == GlobalSymbolsEnum.REVERT
                ):
                    has_return = True
                    break
                elif isinstance(stmt.expression, Return) or isinstance(
                    stmt.expression, RevertStatement
                ):
                    has_return = True
                    break
            elif isinstance(stmt, Return) or isinstance(stmt, RevertStatement):
                has_return = True
                break
            elif isinstance(stmt, InlineAssembly) and stmt.yul_block is not None:
                for yul_stmt in stmt.yul_block.statements:
                    if (
                        isinstance(yul_stmt, YulExpressionStatement)
                        and isinstance(yul_stmt.expression, YulFunctionCall)
                        and yul_stmt.expression.function_name.name
                        in ("revert", "return")
                    ):
                        has_return = True
                        break
        if not has_return:
            has_return_params_named = True
            for param in node.return_parameters.parameters:
                if param.name == "":
                    has_return_params_named = False
                    break

            if not has_return_params_named:
                detections.append(
                    DetectorResult(
                        node,
                        "Not all code paths have return or revert statement",
                        lsp_range=node.name_location,
                    )
                )
            else:
                solved, params = check_all_return_params_set(
                    node.return_parameters.parameters, graph, block, cfg.start_block
                )
                if not solved:
                    detections.append(
                        DetectorResult(
                            node,
                            "Not all code paths have return or revert statement and the return values "
                            "are not set either",
                            lsp_range=node.name_location,
                        )
                    )
    return detections


@detector(-1030, "missing-return")
class MissingReturnDetector(DetectorAbc):
    """
    Detector that checks if all possible paths have a return or revert statement or have all
    return values set
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_definition(self, node: FunctionDefinition):
        if (
            node.body is None
            or len(node.body.statements) == 0
            or len(node.return_parameters.parameters) == 0
        ):
            return

        for det in check_missing_return(node):
            self._detections.add(det)
