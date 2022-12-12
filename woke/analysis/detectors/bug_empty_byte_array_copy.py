from typing import List, Optional, Set

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.analysis.detectors.utils import get_function_definition_from_expression
from woke.ast.enums import DataLocation, GlobalSymbolsEnum
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.assignment import Assignment
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.index_access import IndexAccess
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.expression_statement import ExpressionStatement
from woke.ast.ir.statement.variable_declaration_statement import (
    VariableDeclarationStatement,
)
from woke.core.solidity_version import SolidityVersionRange, SolidityVersionRanges


def check_bug_empty_byte_array_copy(fc: FunctionCall) -> Optional[DetectorResult]:
    versions = fc.version_ranges
    affected_versions = SolidityVersionRanges(
        [SolidityVersionRange(None, None, "0.7.14", False)]
    )
    if len(versions & affected_versions) == 0:
        return None

    # detects data.push()
    if (
        fc.function_called != GlobalSymbolsEnum.BYTES_PUSH
        or not isinstance(fc.expression, MemberAccess)
        or not isinstance(fc.expression.expression, Identifier)
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
    while var_ident_stmt.parent and not isinstance(var_ident_stmt, StatementAbc):
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

        if isinstance(stmt, ExpressionStatement) and isinstance(
            stmt.expression, Assignment
        ):
            # detects data = t;
            if data_decl is None:
                if (
                    isinstance(stmt.expression.left_expression, Identifier)
                    and stmt.expression.left_expression.referenced_declaration
                    == var_ident.referenced_declaration
                    and stmt.expression.right_expression
                    and isinstance(stmt.expression.right_expression, Identifier)
                ):
                    data_decl = stmt.expression.left_expression.referenced_declaration
                    local_variable_decl = (
                        stmt.expression.right_expression.referenced_declaration
                    )
            # detects storing something in the memory
            elif (
                data_decl
                and isinstance(stmt.expression.left_expression, IndexAccess)
                and isinstance(
                    stmt.expression.left_expression.base_expression, Identifier
                )
                and isinstance(
                    stmt.expression.left_expression.base_expression.referenced_declaration,
                    VariableDeclaration,
                )
                and stmt.expression.left_expression.base_expression.referenced_declaration.data_location
                == DataLocation.MEMORY
            ):
                memory_write = True
        # detects variable declaration in memory
        elif (
            data_decl
            and memory_write
            and isinstance(stmt, VariableDeclarationStatement)
        ):
            for dec in stmt.declarations:
                if dec == local_variable_decl:
                    return DetectorResult(
                        fc, "Possible sequence leading to the empty byte array copy bug"
                    )
    return None


@detector(-1020, "bug-empty-byte-array-copy")
class BugEmptyByteArrayCopyDetector(DetectorAbc):
    """
    Detects empty array copy bug for solidity versions < 0.7.14
    (https://blog.soliditylang.org/2020/10/19/empty-byte-array-copy-bug/)
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def visit_function_call(self, node: FunctionCall):
        res = check_bug_empty_byte_array_copy(node)
        if res:
            self._detections.add(res)
