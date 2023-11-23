from __future__ import annotations

from typing import List, Set, Tuple

import networkx as nx
import rich_click as click

import wake.ir as ir
import wake.ir.types as types
from wake.detectors import (
    Detection,
    Detector,
    DetectorConfidence,
    DetectorImpact,
    DetectorResult,
    detector,
)
from wake_detectors.utils import generate_detector_uri


def check_delegatecall_in_function(
    function_definition: ir.FunctionDefinition,
    statement: ir.StatementAbc,
    address_source: ir.ExpressionAbc,
    checked_statements: Set[ir.StatementAbc],
) -> List[Tuple[Detection, DetectorConfidence]]:
    from wake.analysis.expressions import find_low_level_call_source_address
    from wake.analysis.ownable import address_is_safe, statement_is_publicly_executable
    from wake.analysis.utils import pair_function_call_arguments

    if not statement_is_publicly_executable(statement):
        return []

    source_address_declaration = find_low_level_call_source_address(address_source)
    is_safe = None
    if source_address_declaration is None:
        pass
        # logger.debug(f"{address_source.source}")
    elif isinstance(source_address_declaration, ir.enums.GlobalSymbol):
        if source_address_declaration == ir.enums.GlobalSymbol.THIS:
            is_safe = True
        elif source_address_declaration in {
            ir.enums.GlobalSymbol.MSG_SENDER,
            ir.enums.GlobalSymbol.TX_ORIGIN,
        }:
            is_safe = False
        else:
            is_safe = None
            # logger.debug(f"{source_address_declaration}:")
    elif isinstance(source_address_declaration, ir.ContractDefinition):
        if source_address_declaration.kind == ir.enums.ContractKind.LIBRARY:
            is_safe = True
    elif isinstance(source_address_declaration, ir.Literal):
        is_safe = True
    else:
        is_safe = address_is_safe(source_address_declaration)

    if is_safe:
        return []

    checked_statements.add(statement)
    ret = []
    if function_definition.visibility in {
        ir.enums.Visibility.PUBLIC,
        ir.enums.Visibility.EXTERNAL,
    }:
        ret.append(
            (
                Detection(
                    statement,
                    f"Exploitable from `{function_definition.canonical_name}`",
                ),
                DetectorConfidence.LOW
                if is_safe is None
                else DetectorConfidence.MEDIUM,
            )
        )

    for ref in function_definition.get_all_references(False):
        if isinstance(ref, ir.IdentifierPathPart):
            top_statement = ref.underlying_node
        elif isinstance(ref, ir.ExternalReference):
            continue  # TODO currently not supported
        else:
            top_statement = ref
        func_call = None
        while top_statement is not None:
            if (
                func_call is None
                and isinstance(top_statement, ir.FunctionCall)
                and top_statement.function_called == function_definition
            ):
                func_call = top_statement
            if isinstance(top_statement, ir.StatementAbc):
                break
            top_statement = top_statement.parent

        if top_statement is None or func_call is None:
            continue
        function_def = top_statement
        while function_def is not None and not isinstance(
            function_def, ir.FunctionDefinition
        ):
            function_def = function_def.parent
        if function_def is None:
            continue
        assert isinstance(function_def, ir.FunctionDefinition)
        if top_statement in checked_statements:
            continue

        if source_address_declaration in function_definition.parameters.parameters:
            for arg_decl, arg_expr in pair_function_call_arguments(
                function_definition, func_call
            ):
                if arg_decl == source_address_declaration:
                    assert isinstance(arg_expr.type, (types.Address, types.Contract))
                    ret.extend(
                        check_delegatecall_in_function(
                            function_def, top_statement, arg_expr, checked_statements
                        )
                    )
                    break
        else:
            ret.extend(
                check_delegatecall_in_function(
                    function_def, top_statement, address_source, checked_statements
                )
            )

    return ret


class UnsafeDelegatecallDetector(Detector):
    _proxy: bool
    _detections: List[DetectorResult]

    def __init__(self):
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_member_access(self, node: ir.MemberAccess):
        from wake.analysis.proxy import contract_is_proxy

        t = node.type
        if (
            not isinstance(t, types.Function)
            or t.kind
            not in {
                ir.enums.FunctionTypeKind.DELEGATE_CALL,
                ir.enums.FunctionTypeKind.BARE_DELEGATE_CALL,
            }
            or t.attached_to is not None
            or node.statement is None
        ):
            return

        func = node.statement.declaration
        # TODO: delegatecalls in modifiers
        if not isinstance(func, ir.FunctionDefinition):
            return

        contract = func.parent
        if (
            not self._proxy
            and isinstance(contract, ir.ContractDefinition)
            and contract_is_proxy(contract)
        ):
            return

        ret = check_delegatecall_in_function(
            func, node.statement, node.expression, set()
        )
        if len(ret) == 0:
            return

        self._detections.append(
            DetectorResult(
                Detection(
                    node,
                    f"Possibly unsafe delegatecall in `{func.canonical_name}`",
                    tuple(r[0] for r in ret),
                ),
                confidence=max(r[1] for r in ret),
                impact=DetectorImpact.MEDIUM,
                uri=generate_detector_uri(
                    name="unsafe-delegatecall",
                    version=self.extra["package_versions"]["eth-wake"],
                ),
            )
        )

    @detector.command(name="unsafe-delegatecall")
    @click.option(
        "--proxy/--no-proxy",
        is_flag=True,
        default=False,
        help="Detect delegatecalls in proxy contracts.",
    )
    def cli(self, proxy: bool) -> None:
        """
        delegatecall to untrusted contract
        """
        self._proxy = proxy
