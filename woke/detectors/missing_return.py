from __future__ import annotations

from typing import List, Set

import woke.ir as ir
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


def check_missing_return(node: ir.FunctionDefinition) -> List[DetectorResult]:
    from woke.analysis.utils import check_all_return_params_set

    cfg = node.cfg
    assert cfg is not None
    end = cfg.end_block
    graph = cfg.graph
    detections = []

    for block in graph.predecessors(end):
        has_return = False
        for stmt in block.statements:
            if isinstance(stmt, ir.ExpressionStatement):
                if (
                    isinstance(stmt.expression, ir.FunctionCall)
                    and stmt.expression.function_called
                    == ir.enums.GlobalSymbolsEnum.REVERT
                ):
                    has_return = True
                    break
                elif isinstance(stmt.expression, ir.Return) or isinstance(
                    stmt.expression, ir.RevertStatement
                ):
                    has_return = True
                    break
            elif isinstance(stmt, ir.Return) or isinstance(stmt, ir.RevertStatement):
                has_return = True
                break
            elif isinstance(stmt, ir.InlineAssembly) and stmt.yul_block is not None:
                for yul_stmt in stmt.yul_block.statements:
                    if (
                        isinstance(yul_stmt, ir.YulExpressionStatement)
                        and isinstance(yul_stmt.expression, ir.YulFunctionCall)
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
                        Detection(
                            node,
                            "Not all code paths have return or revert statement",
                            lsp_range=node.name_location,
                        ),
                        DetectionImpact.MEDIUM,
                        DetectionConfidence.LOW,
                    )
                )
            else:
                solved, params = check_all_return_params_set(
                    node.return_parameters.parameters, graph, block, cfg.start_block
                )
                if not solved:
                    detections.append(
                        DetectorResult(
                            Detection(
                                node,
                                "Not all code paths have return or revert statement and the return values "
                                "are not set either",
                                lsp_range=node.name_location,
                            ),
                            DetectionImpact.MEDIUM,
                            DetectionConfidence.LOW,
                        )
                    )
    return detections


class MissingReturnDetector(Detector):
    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_definition(self, node: ir.FunctionDefinition):
        if (
            node.body is None
            or len(node.body.statements) == 0
            or len(node.return_parameters.parameters) == 0
        ):
            return

        for det in check_missing_return(node):
            self._detections.add(det)

    @detector.command("missing-return")
    def cli(self):
        """
        Detector that checks if all possible paths have a return or revert statement or have all
        return values set
        """
        pass
