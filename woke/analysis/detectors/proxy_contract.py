from functools import lru_cache
from typing import List, Optional, Set, Tuple, Union

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.analysis.detectors.utils import (
    get_function_implementations,
    pair_function_call_arguments,
)
from woke.ast.enums import FunctionKind, GlobalSymbolsEnum, LiteralKind
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.binary_operation import BinaryOperation
from woke.ast.ir.expression.function_call import FunctionCall
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.expression.literal import Literal
from woke.ast.ir.expression.member_access import MemberAccess
from woke.ast.ir.expression.tuple_expression import TupleExpression
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.inline_assembly import InlineAssembly
from woke.ast.ir.statement.return_statement import Return
from woke.ast.ir.statement.variable_declaration_statement import (
    VariableDeclarationStatement,
)
from woke.ast.ir.yul.block import Block as YulBlock
from woke.ast.ir.yul.function_call import FunctionCall as YulFunctionCall
from woke.ast.ir.yul.identifier import Identifier as YulIdentifier
from woke.ast.types import Address, FixedBytes


@lru_cache(maxsize=2048)
def detect_slot_value(expr: ExpressionAbc) -> Optional[DetectorResult]:
    val = expr
    while True:
        if isinstance(val, Literal) and val.kind in (
            LiteralKind.NUMBER,
            LiteralKind.STRING,
        ):
            return DetectorResult(val, "Detected slot in upgrade contract")
        elif isinstance(val, BinaryOperation) and isinstance(
            val.left_expression, FunctionCall
        ):
            val = val.left_expression
        elif isinstance(val, BinaryOperation) and isinstance(
            val.right_expression, FunctionCall
        ):
            val = val.right_expression
        elif (
            isinstance(val, FunctionCall)
            and val.function_called != GlobalSymbolsEnum.KECCAK256
            and len(val.arguments) == 1
        ):
            val = val.arguments[0]
        else:
            break
    if (
        isinstance(val, FunctionCall)
        and val.function_called == GlobalSymbolsEnum.KECCAK256
    ):
        return DetectorResult(
            expr, "Detected slot through keccak256 in upgrade contract"
        )
    return None


@lru_cache(maxsize=2048)
def detect_implementation_fn(fn: FunctionDefinition) -> List[DetectorResult]:
    dets = []
    if fn.body is None:
        for fn_impl in get_function_implementations(fn):
            if not isinstance(fn_impl, FunctionDefinition):
                continue
            dets.extend(detect_implementation_fn(fn_impl))
        return dets

    addr_detected = False
    for param in fn.return_parameters.parameters:
        if isinstance(param.type, Address):
            addr_detected = True
    if not addr_detected:
        return dets

    dets = []
    for node in fn.body:
        if isinstance(node, Return) and node.expression is not None:
            for det in detect_slot_variable(node.expression):
                dets.append(
                    DetectorResult(
                        fn,
                        "Detected slot usage in implementation function",
                        related_info=(det,),
                    )
                )
        elif isinstance(node, FunctionCall) and isinstance(
            node.function_called, FunctionDefinition
        ):
            for det in detect_implementation_fn(node.function_called):
                dets.append(
                    DetectorResult(
                        fn,
                        "Detected implementation function",
                        related_info=(det,),
                    )
                )
        elif isinstance(node, InlineAssembly) and node.yul_block is not None:
            for det in check_assembly_uses_slot_variable(node.yul_block):
                dets.append(
                    DetectorResult(
                        fn,
                        "Detected slot usage in implementation function",
                        related_info=(det,),
                    )
                )
    return dets


def check_functioncall(fc: FunctionCall) -> List[DetectorResult]:
    dets = []
    for arg in fc.arguments:
        det = detect_slot_variable(arg)
        if len(det) > 0:
            dets.extend(det)
    if isinstance(fc.function_called, FunctionDefinition):
        det = detect_implementation_fn(fc.function_called)
        if len(det) > 0:
            dets.extend(det)
    return dets


def detect_slot_variable(
    expr: Union[ExpressionAbc, DeclarationAbc, StatementAbc],
    value: Optional[ExpressionAbc] = None,
    visited=None,
) -> List[DetectorResult]:
    dets = []
    if visited is None:
        visited = set()
    if (expr, value) in visited:
        return dets
    visited.add((expr, value))

    if isinstance(expr, TupleExpression):
        for t in expr:
            if isinstance(t, ExpressionAbc) or isinstance(t, DeclarationAbc):
                dets.extend(detect_slot_variable(t, visited=visited))
    elif isinstance(expr, VariableDeclaration):
        val = expr.value if expr.value is not None else value
        if (
            expr.is_state_variable
            and isinstance(expr.type, FixedBytes)
            and expr.type.bytes_count == 32
        ):
            if val is not None:
                det = detect_slot_value(val)
                if det is not None:
                    dets.append(det)
        elif isinstance(expr.type, Address):
            if val is not None:
                det = detect_slot_value(val)
                if det is not None:
                    dets.append(det)
                if isinstance(val, FunctionCall) and isinstance(
                    val.function_called, FunctionDefinition
                ):
                    for arg in val.arguments:
                        dets.extend(detect_slot_variable(arg, visited=visited))
                    dets.extend(detect_implementation_fn(val.function_called))
            elif expr.parent is not None and isinstance(
                expr.parent, VariableDeclarationStatement
            ):
                dets.extend(detect_slot_variable(expr.parent, visited=visited))
    elif (
        isinstance(expr, VariableDeclarationStatement)
        and expr.initial_value is not None
        and (
            (
                isinstance(expr.initial_value, TupleExpression)
                and len(expr.declarations) == len(expr.initial_value.components)
            )
            or (len(expr.declarations) == 1)
        )
    ):
        if isinstance(expr.initial_value, TupleExpression):
            vals = expr.initial_value.components
        elif isinstance(expr.initial_value, ExpressionAbc):
            vals = [expr.initial_value]
        elif isinstance(expr.initial_value, List):
            vals = expr.initial_value
        else:
            return dets
        for i in range(len(vals)):
            ini_val = vals[i]
            if isinstance(ini_val, Identifier) and isinstance(
                ini_val.referenced_declaration, VariableDeclaration
            ):
                dets.extend(
                    detect_slot_variable(
                        ini_val.referenced_declaration, visited=visited
                    )
                )
            elif isinstance(ini_val, ExpressionAbc) and ini_val is not None:
                decl = expr.declarations[i]
                if decl is not None:
                    dets.extend(detect_slot_variable(decl, ini_val, visited=visited))
    elif (
        isinstance(expr, Identifier)
        and isinstance(expr.referenced_declaration, VariableDeclaration)
        and expr.is_ref_to_state_variable
    ):
        dets.extend(detect_slot_variable(expr.referenced_declaration, visited=visited))
    elif isinstance(expr, MemberAccess):
        for n in expr:
            if n == expr:
                continue
            if isinstance(n, ExpressionAbc) or isinstance(n, DeclarationAbc):
                dets.extend(detect_slot_variable(n, visited=visited))
    return dets


def detect_delegatecall_to_slot_variable(
    fn: FunctionDefinition,
    callargs: Optional[Tuple[Tuple[VariableDeclaration, ExpressionAbc], ...]],
    visited=None,
) -> List[DetectorResult]:
    dets = []
    if visited is None:
        visited = []
    if fn in visited:
        return dets
    visited.append(fn)

    if fn.body is None:
        for impl in get_function_implementations(fn):
            if isinstance(impl, FunctionDefinition):
                dets.extend(
                    detect_delegatecall_to_slot_variable(impl, callargs, visited)
                )
        return dets

    for node in fn.body:
        if isinstance(node, FunctionCall):
            if isinstance(node.function_called, FunctionDefinition):
                for det in detect_delegatecall_to_slot_variable(
                    node.function_called,
                    pair_function_call_arguments(node.function_called, node),
                    visited,
                ):
                    dets.append(
                        DetectorResult(node, "Detected call", related_info=(det,))
                    )
            elif (
                node.function_called == GlobalSymbolsEnum.ADDRESS_DELEGATECALL
                and len(node.arguments) == 1
            ):
                if isinstance(node.expression, MemberAccess) and isinstance(
                    node.expression.referenced_declaration, DeclarationAbc
                ):
                    for det in detect_slot_variable(
                        node.expression.referenced_declaration
                    ):
                        dets.append(
                            DetectorResult(
                                fn,
                                "Detected delegate call to an implementation slot",
                                related_info=(
                                    DetectorResult(
                                        node, "Detected call", related_info=(det,)
                                    ),
                                ),
                            )
                        )
        elif (
            isinstance(node, YulFunctionCall)
            and node.function_name.name == "delegatecall"
            and len(node.arguments) > 1
        ):
            arg = node.arguments[1]  # type: ignore
            if isinstance(arg, YulIdentifier) and arg.external_reference is not None:
                ref_decl = arg.external_reference.referenced_declaration
                assembly_dets = []
                if (
                    ref_decl in fn.parameters.parameters
                    and len(fn.parameters.parameters) > 0
                    and callargs is not None
                    and fn.parameters.parameters.index(ref_decl) < len(callargs)
                ):
                    assembly_dets = detect_slot_variable(
                        ref_decl, callargs[fn.parameters.parameters.index(ref_decl)][1]
                    )
                else:
                    assembly_dets = detect_slot_variable(ref_decl)
                for det in assembly_dets:
                    dets.append(
                        DetectorResult(
                            fn,
                            "Detected assembly delegate call using an implementation slot",
                            related_info=(
                                DetectorResult(
                                    node,
                                    "Detected assembly call",
                                    related_info=(
                                        DetectorResult(
                                            ref_decl,
                                            "Detected reference with implementation value passed in callargs",
                                            related_info=(det,),
                                        ),
                                    ),
                                ),
                            ),
                        )
                    )
    return dets


def check_assembly_uses_slot_variable(block: YulBlock) -> List[DetectorResult]:
    dets = []
    if block.statements is None:
        return dets

    for yul in block:
        if isinstance(yul, YulIdentifier):
            if yul.external_reference is not None:
                for det in detect_slot_variable(
                    yul.external_reference.referenced_declaration
                ):
                    dets.append(
                        DetectorResult(
                            yul,
                            "Detected slot variable usage in assembly",
                            related_info=(det,),
                        )
                    )
    return dets


def detect_fallback(fn: FunctionDefinition) -> List[DetectorResult]:
    dets = []
    if fn.kind != FunctionKind.FALLBACK:
        return dets

    if fn.body is None:
        return dets

    for det in detect_delegatecall_to_slot_variable(fn, None):
        dets.append(
            DetectorResult(
                fn,
                "Detected fallback function with delegate call to an implementation slot",
                related_info=(det,),
            )
        )
    return dets


def get_last_detection_node(det: DetectorResult) -> IrAbc:
    if len(det.related_info) == 0:
        return det.ir_node
    return get_last_detection_node(det.related_info[0])


def detect_slot_usage(fn: FunctionDefinition, visited=None) -> List[DetectorResult]:
    dets = []
    if visited is None:
        visited = []
    if fn in visited:
        return dets
    visited.append(fn)
    if fn.body is None:
        return dets

    if not fn.implemented:
        for impl_fn in get_function_implementations(fn):
            if isinstance(impl_fn, FunctionDefinition):
                dets.extend(detect_slot_usage(impl_fn, visited=visited))
        return dets
    for node in fn.body:
        if (
            isinstance(node, Identifier) or isinstance(node, MemberAccess)
        ) and isinstance(node.referenced_declaration, DeclarationAbc):
            for det in detect_slot_variable(node.referenced_declaration):
                dets.append(
                    DetectorResult(
                        node,
                        "Detected slot variable usage",
                        related_info=(det,),
                    )
                )
        elif isinstance(node, FunctionCall) and isinstance(
            node.function_called, FunctionDefinition
        ):
            for det in detect_slot_usage(node.function_called, visited=visited):
                dets.append(
                    DetectorResult(
                        node,
                        "Detected slot variable usage",
                        related_info=(det,),
                    )
                )
        elif isinstance(node, InlineAssembly) and node.yul_block is not None:
            for det in check_assembly_uses_slot_variable(node.yul_block):
                dets.append(
                    DetectorResult(
                        node,
                        "Detected slot variable usage",
                        related_info=(det,),
                    )
                )
    return dets


@detector(-1030, "detect_proxy_contract")
class ProxyContractDetector(DetectorAbc):
    """
    Detects proxy contracts based on fallback function and usage of slot variables and
    implementation contracts that use same slots as proxy contracts
    """

    _proxy_detections: Set[Tuple[ContractDefinition, DetectorResult]]
    _proxy_associated_contracts: Set[ContractDefinition]
    _implementation_slots_detections: Set[Tuple[ContractDefinition, DetectorResult]]
    _implementation_slots: Set[VariableDeclaration]

    def __init__(self):
        self._proxy_detections: Set[Tuple[ContractDefinition, DetectorResult]] = set()
        self._proxy_associated_contracts: Set[ContractDefinition] = set()
        self._implementation_slots_detections: Set[
            Tuple[ContractDefinition, DetectorResult]
        ] = set()
        self._implementation_slots: Set[VariableDeclaration] = set()

    def report(self) -> List[DetectorResult]:
        detections = []

        base_proxy_contracts = set()
        for (contract, _) in self._proxy_detections:
            for c in contract.linearized_base_contracts:
                if c == contract:
                    continue
                base_proxy_contracts.add(c)

        for (contract, det) in self._proxy_detections:
            if contract not in base_proxy_contracts:
                detections.append(det)

        base_impl_contracts = set()
        for (contract, _) in self._implementation_slots_detections:
            for c in contract.linearized_base_contracts:
                if c == contract:
                    continue
                base_impl_contracts.add(c)

        impl_detections_contracts = set()
        for (contract, det) in self._implementation_slots_detections:
            if (
                contract not in self._proxy_associated_contracts
                and contract not in base_impl_contracts
                and get_last_detection_node(det).parent in self._implementation_slots
                and contract not in impl_detections_contracts
            ):
                impl_detections_contracts.add(contract)
                detections.append(
                    DetectorResult(
                        contract,
                        "Detected implementation contract with slot used in proxy contract",
                        related_info=(det,),
                    )
                )
        return list(detections)

    def visit_contract_definition(self, node: ContractDefinition):
        searched_fns = set()
        if node not in self._proxy_associated_contracts:
            for b in node.linearized_base_contracts:
                for f in b.functions:
                    if f.implemented and f not in searched_fns:
                        searched_fns.add(f)
                        dets = detect_fallback(f)
                        if len(dets) > 0:
                            self._proxy_detections.add(
                                (
                                    node,
                                    DetectorResult(
                                        node,
                                        "Detected proxy contract",
                                        related_info=tuple(dets),
                                    ),
                                )
                            )
                            for det in dets:
                                last_det_node = get_last_detection_node(det)
                                if isinstance(
                                    last_det_node.parent, VariableDeclaration
                                ):
                                    self._implementation_slots.add(last_det_node.parent)
                                self._proxy_associated_contracts.add(node)
                                for bc in node.linearized_base_contracts:
                                    self._proxy_associated_contracts.add(bc)

        if node not in self._proxy_associated_contracts:
            for fn in node.functions:
                for det in detect_slot_usage(fn):
                    self._implementation_slots_detections.add((node, det))
