from __future__ import annotations

from typing import List, Optional, Set

import woke.ir as ir
from woke.core.solidity_version import SolidityVersionRange, SolidityVersionRanges
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


def check_bug_empty_byte_array_copy(fc: ir.FunctionCall) -> Optional[Detection]:
    from woke.analysis.utils import get_function_definition_from_expression

    versions = fc.version_ranges
    affected_versions = SolidityVersionRanges(
        [SolidityVersionRange(None, None, "0.7.14", False)]
    )
    if len(versions & affected_versions) == 0:
        return None

    # detects data.push()
    if (
        fc.function_called != ir.enums.GlobalSymbolsEnum.BYTES_PUSH
        or not isinstance(fc.expression, ir.MemberAccess)
        or not isinstance(fc.expression.expression, ir.Identifier)
        or len(fc.arguments) != 0
    ):
        return None

    var_ident = fc.expression.expression
    if not var_ident.is_ref_to_state_variable or not var_ident:
        return None

    fn_def = get_function_definition_from_expression(fc)
    if not fn_def or not fn_def.body:
        return None

    var_ident_stmt = var_ident
    while var_ident_stmt.parent and not isinstance(var_ident_stmt, ir.StatementAbc):
        var_ident_stmt = var_ident_stmt.parent
    if not var_ident_stmt:
        return None

    start = False
    memory_write = False
    data_decl = None
    local_variable_decl = None
    for stmt in reversed(list(fn_def.body.statements_iter())):
        if stmt == var_ident_stmt:
            start = True
        if not start:
            continue

        if isinstance(stmt, ir.ExpressionStatement) and isinstance(
            stmt.expression, ir.Assignment
        ):
            # detects data = t;
            if data_decl is None:
                if (
                    isinstance(stmt.expression.left_expression, ir.Identifier)
                    and stmt.expression.left_expression.referenced_declaration
                    == var_ident.referenced_declaration
                    and stmt.expression.right_expression
                    and isinstance(stmt.expression.right_expression, ir.Identifier)
                ):
                    data_decl = stmt.expression.left_expression.referenced_declaration
                    local_variable_decl = (
                        stmt.expression.right_expression.referenced_declaration
                    )
            # detects storing something in the memory
            elif (
                data_decl
                and isinstance(stmt.expression.left_expression, ir.IndexAccess)
                and isinstance(
                    stmt.expression.left_expression.base_expression, ir.Identifier
                )
                and isinstance(
                    stmt.expression.left_expression.base_expression.referenced_declaration,
                    ir.VariableDeclaration,
                )
                and stmt.expression.left_expression.base_expression.referenced_declaration.data_location
                == ir.enums.DataLocation.MEMORY
            ):
                memory_write = True
        # detects variable declaration in memory
        elif (
            data_decl
            and memory_write
            and isinstance(stmt, ir.VariableDeclarationStatement)
        ):
            for dec in stmt.declarations:
                if dec == local_variable_decl:
                    return Detection(
                        fc, "Possible sequence leading to the empty byte array copy bug"
                    )
    return None


class BugEmptyByteArrayCopyDetector(Detector):
    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_call(self, node):
        res = check_bug_empty_byte_array_copy(node)
        if res:
            self._detections.add(
                DetectorResult(
                    res,
                    impact=DetectionImpact.HIGH,
                    confidence=DetectionConfidence.HIGH,
                )
            )

    @detector.command("bug-empty-byte-array-copy")
    def cli(self):
        """
        Detects empty array copy bug for solidity versions < 0.7.14
        (https://blog.soliditylang.org/2020/10/19/empty-byte-array-copy-bug/)
        """
        pass
