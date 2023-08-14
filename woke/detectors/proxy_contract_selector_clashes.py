from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, Union

import woke.ir as ir
import woke.ir.types as types
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


@lru_cache(maxsize=2048)
def _detect_slot_value(expr: ir.ExpressionAbc) -> Optional[Detection]:

    val = expr
    while True:
        if isinstance(val, ir.Literal) and val.kind in (
            ir.enums.LiteralKind.NUMBER,
            ir.enums.LiteralKind.STRING,
        ):
            return Detection(val, "Detected slot in upgrade contract")
        elif isinstance(val, ir.BinaryOperation) and isinstance(
            val.left_expression, ir.FunctionCall
        ):
            val = val.left_expression
        elif isinstance(val, ir.BinaryOperation) and isinstance(
            val.right_expression, ir.FunctionCall
        ):
            val = val.right_expression
        elif (
            isinstance(val, ir.FunctionCall)
            and val.function_called != ir.enums.GlobalSymbolsEnum.KECCAK256
            and len(val.arguments) == 1
        ):
            val = val.arguments[0]
        else:
            break
    if (
        isinstance(val, ir.FunctionCall)
        and val.function_called == ir.enums.GlobalSymbolsEnum.KECCAK256
    ):
        return Detection(expr, "Detected slot through keccak256 in upgrade contract")
    return None


@lru_cache(maxsize=2048)
def _detect_implementation_fn(fn: ir.FunctionDefinition) -> List[Detection]:
    from woke.analysis.utils import get_function_implementations

    dets = []
    if fn.body is None:
        for fn_impl in get_function_implementations(fn):
            if not isinstance(fn_impl, ir.FunctionDefinition):
                continue
            dets.extend(_detect_implementation_fn(fn_impl))
        return dets

    addr_detected = False
    for param in fn.return_parameters.parameters:
        if isinstance(param.type, types.Address):
            addr_detected = True
    if not addr_detected:
        return dets

    dets = []
    for node in fn.body:
        if isinstance(node, ir.Return) and node.expression is not None:
            for det in _detect_slot_variable(node.expression):
                dets.append(
                    Detection(
                        fn,
                        "Detected slot usage in implementation function",
                        subdetections=(det,),
                        lsp_range=fn.name_location,
                    )
                )
        elif isinstance(node, ir.FunctionCall) and isinstance(
            node.function_called, ir.FunctionDefinition
        ):
            for det in _detect_implementation_fn(node.function_called):
                dets.append(
                    Detection(
                        fn,
                        "Detected implementation function",
                        subdetections=(det,),
                        lsp_range=fn.name_location,
                    )
                )
        elif isinstance(node, ir.InlineAssembly) and node.yul_block is not None:
            for det in _check_assembly_uses_slot_variable(node.yul_block):
                dets.append(
                    Detection(
                        fn,
                        "Detected slot usage in implementation function",
                        subdetections=(det,),
                        lsp_range=fn.name_location,
                    )
                )
    return dets


def _detect_slot_variable(
    expr: Union[ir.ExpressionAbc, ir.DeclarationAbc, ir.StatementAbc],
    value: Optional[ir.ExpressionAbc] = None,
    visited=None,
) -> List[Detection]:
    dets = []
    if visited is None:
        visited = set()
    if (expr, value) in visited:
        return dets
    visited.add((expr, value))

    if isinstance(expr, ir.TupleExpression):
        for t in expr:
            if isinstance(t, ir.ExpressionAbc) or isinstance(t, ir.DeclarationAbc):
                dets.extend(_detect_slot_variable(t, visited=visited))
    elif isinstance(expr, ir.VariableDeclaration):
        val = expr.value if expr.value is not None else value
        if (
            expr.is_state_variable
            and isinstance(expr.type, types.FixedBytes)
            and expr.type.bytes_count == 32
        ):
            if val is not None:
                det = _detect_slot_value(val)
                if det is not None:
                    dets.append(det)
        elif isinstance(expr.type, types.Address):
            if val is not None:
                det = _detect_slot_value(val)
                if det is not None:
                    dets.append(det)
                if isinstance(val, ir.FunctionCall) and isinstance(
                    val.function_called, ir.FunctionDefinition
                ):
                    for arg in val.arguments:
                        dets.extend(_detect_slot_variable(arg, visited=visited))
                    dets.extend(_detect_implementation_fn(val.function_called))
            elif expr.parent is not None and isinstance(
                expr.parent, ir.VariableDeclarationStatement
            ):
                dets.extend(_detect_slot_variable(expr.parent, visited=visited))
    elif (
        isinstance(expr, ir.VariableDeclarationStatement)
        and expr.initial_value is not None
        and (
            (
                isinstance(expr.initial_value, ir.TupleExpression)
                and len(expr.declarations) == len(expr.initial_value.components)
            )
            or (len(expr.declarations) == 1)
        )
    ):
        if isinstance(expr.initial_value, ir.TupleExpression):
            vals = expr.initial_value.components
        elif isinstance(expr.initial_value, ir.ExpressionAbc):
            vals = [expr.initial_value]
        elif isinstance(expr.initial_value, List):
            vals = expr.initial_value
        else:
            return dets
        for i in range(len(vals)):
            ini_val = vals[i]
            if isinstance(ini_val, ir.Identifier) and isinstance(
                ini_val.referenced_declaration, ir.VariableDeclaration
            ):
                dets.extend(
                    _detect_slot_variable(
                        ini_val.referenced_declaration, visited=visited
                    )
                )
            elif isinstance(ini_val, ir.ExpressionAbc) and ini_val is not None:
                decl = expr.declarations[i]
                if decl is not None:
                    dets.extend(_detect_slot_variable(decl, ini_val, visited=visited))
    elif (
        isinstance(expr, ir.Identifier)
        and isinstance(expr.referenced_declaration, ir.VariableDeclaration)
        and expr.is_ref_to_state_variable
    ):
        dets.extend(_detect_slot_variable(expr.referenced_declaration, visited=visited))
    elif isinstance(expr, ir.MemberAccess):
        for n in expr:
            if n == expr:
                continue
            if isinstance(n, ir.ExpressionAbc) or isinstance(n, ir.DeclarationAbc):
                dets.extend(_detect_slot_variable(n, visited=visited))
    return dets


def _detect_delegatecall_to_slot_variable(
    fn: ir.FunctionDefinition,
    callargs: Optional[Tuple[Tuple[ir.VariableDeclaration, ir.ExpressionAbc], ...]],
    visited=None,
) -> List[Detection]:
    from woke.analysis.utils import (
        get_function_implementations,
        pair_function_call_arguments,
    )

    dets = []
    if visited is None:
        visited = []
    if fn in visited:
        return dets
    visited.append(fn)

    if fn.body is None:
        for impl in get_function_implementations(fn):
            if isinstance(impl, ir.FunctionDefinition):
                dets.extend(
                    _detect_delegatecall_to_slot_variable(impl, callargs, visited)
                )
        return dets

    for node in fn.body:
        if isinstance(node, ir.FunctionCall):
            if isinstance(node.function_called, ir.FunctionDefinition):
                for det in _detect_delegatecall_to_slot_variable(
                    node.function_called,
                    pair_function_call_arguments(node.function_called, node),
                    visited,
                ):
                    dets.append(Detection(node, "Detected call", subdetections=(det,)))
            elif (
                node.function_called == ir.enums.GlobalSymbolsEnum.ADDRESS_DELEGATECALL
                and len(node.arguments) == 1
            ):
                if isinstance(node.expression, ir.MemberAccess) and isinstance(
                    node.expression.referenced_declaration, ir.DeclarationAbc
                ):
                    for det in _detect_slot_variable(
                        node.expression.referenced_declaration
                    ):
                        dets.append(
                            Detection(
                                fn,
                                "Detected delegate call to an implementation slot",
                                subdetections=(
                                    Detection(
                                        node, "Detected call", subdetections=(det,)
                                    ),
                                ),
                                lsp_range=fn.name_location,
                            )
                        )
        elif (
            isinstance(node, ir.YulFunctionCall)
            and node.function_name.name == "delegatecall"
            and len(node.arguments) > 1
        ):
            arg = node.arguments[1]  # type: ignore
            if isinstance(arg, ir.YulIdentifier) and arg.external_reference is not None:
                ref_decl = arg.external_reference.referenced_declaration
                assembly_dets = []
                if (
                    ref_decl in fn.parameters.parameters
                    and len(fn.parameters.parameters) > 0
                    and callargs is not None
                    and fn.parameters.parameters.index(ref_decl) < len(callargs)
                ):
                    assembly_dets = _detect_slot_variable(
                        ref_decl, callargs[fn.parameters.parameters.index(ref_decl)][1]
                    )
                else:
                    assembly_dets = _detect_slot_variable(ref_decl)
                for det in assembly_dets:
                    dets.append(
                        Detection(
                            fn,
                            "Detected assembly delegate call using an implementation slot",
                            subdetections=(
                                Detection(
                                    node,
                                    "Detected assembly call",
                                    subdetections=(
                                        Detection(
                                            ref_decl,
                                            "Detected reference with implementation value passed in callargs",
                                            subdetections=(det,),
                                        ),
                                    ),
                                ),
                            ),
                            lsp_range=fn.name_location,
                        )
                    )
    return dets


def _check_assembly_uses_slot_variable(block: ir.YulBlock) -> List[Detection]:
    dets = []
    if block.statements is None:
        return dets

    for yul in block:
        if isinstance(yul, ir.YulIdentifier):
            if yul.external_reference is not None:
                for det in _detect_slot_variable(
                    yul.external_reference.referenced_declaration
                ):
                    dets.append(
                        Detection(
                            yul,
                            "Detected slot variable usage in assembly",
                            subdetections=(det,),
                        )
                    )
    return dets


def detect_fallback(fn: ir.FunctionDefinition) -> List[Detection]:
    dets = []
    if fn.kind != ir.enums.FunctionKind.FALLBACK:
        return dets

    if fn.body is None:
        return dets

    for det in _detect_delegatecall_to_slot_variable(fn, None):
        dets.append(
            Detection(
                fn,
                "Detected fallback function with delegate call to an implementation slot",
                subdetections=(det,),
                lsp_range=fn.name_location,
            )
        )
    return dets


def get_last_detection_node(det: Detection) -> ir.IrAbc:
    if len(det.subdetections) == 0:
        return det.ir_node
    return get_last_detection_node(det.subdetections[0])


def detect_slot_usage(fn: ir.FunctionDefinition, visited=None) -> List[Detection]:
    from woke.analysis.utils import get_function_implementations

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
            if isinstance(impl_fn, ir.FunctionDefinition):
                dets.extend(detect_slot_usage(impl_fn, visited=visited))
        return dets
    for node in fn.body:
        if (
            isinstance(node, ir.Identifier) or isinstance(node, ir.MemberAccess)
        ) and isinstance(node.referenced_declaration, ir.DeclarationAbc):
            for det in _detect_slot_variable(node.referenced_declaration):
                dets.append(
                    Detection(
                        node,
                        "Detected slot variable usage",
                        subdetections=(det,),
                    )
                )
        elif isinstance(node, ir.FunctionCall) and isinstance(
            node.function_called, ir.FunctionDefinition
        ):
            for det in detect_slot_usage(node.function_called, visited=visited):
                dets.append(
                    Detection(
                        node,
                        "Detected slot variable usage",
                        subdetections=(det,),
                    )
                )
        elif isinstance(node, ir.InlineAssembly) and node.yul_block is not None:
            for det in _check_assembly_uses_slot_variable(node.yul_block):
                dets.append(
                    Detection(
                        node,
                        "Detected slot variable usage",
                        subdetections=(det,),
                    )
                )
    return dets


def detect_selector_clashes(
    proxy_contract: ir.ContractDefinition,
    impl_contract: ir.ContractDefinition,
    proxy_detection: Detection,
    impl_detection: Detection,
) -> List[DetectorResult]:
    fn_whitelist = ["implementation"]

    proxy_selectors = {}
    for c in proxy_contract.linearized_base_contracts:
        for f in c.functions + c.declared_variables:
            if f.function_selector is not None:
                proxy_selectors[f.function_selector] = f

    impl_selectors = {}
    for c in impl_contract.linearized_base_contracts:
        for f in c.functions + c.declared_variables:
            if f.function_selector is not None:
                impl_selectors[f.function_selector] = f

    clashes = []
    for proxy_sel, proxy_fn in proxy_selectors.items():
        if (
            isinstance(proxy_fn, ir.FunctionDefinition)
            and proxy_fn.name in fn_whitelist
        ):
            continue
        if proxy_sel in impl_selectors:
            clashes.append(
                DetectorResult(
                    Detection(
                        proxy_fn,
                        "Detected selector clash with implementation contract",
                        subdetections=(
                            Detection(
                                impl_selectors[proxy_sel],
                                "Implementation function with same selector",
                                subdetections=(impl_detection,),
                                lsp_range=impl_selectors[proxy_sel].name_location
                                if isinstance(
                                    impl_selectors[proxy_sel], ir.FunctionDefinition
                                )
                                else None,
                            ),
                            proxy_detection,
                        ),
                        lsp_range=proxy_fn.name_location,
                    ),
                    confidence=DetectionConfidence.MEDIUM,
                    impact=DetectionImpact.MEDIUM,
                )
            )
    return clashes


class ProxyContractSelectorClashDetector(Detector):
    _proxy_detections: Set[Tuple[ir.ContractDefinition, Detection]]
    _proxy_associated_contracts: Set[ir.ContractDefinition]
    _implementation_slots_detections: Set[Tuple[ir.ContractDefinition, Detection]]
    _implementation_slots: Dict[ir.VariableDeclaration, List[ir.ContractDefinition]]

    def __init__(self):
        self._proxy_detections: Set[Tuple[ir.ContractDefinition, Detection]] = set()
        self._proxy_associated_contracts: Set[ir.ContractDefinition] = set()
        self._implementation_slots_detections: Set[
            Tuple[ir.ContractDefinition, Detection]
        ] = set()
        self._implementation_slots: Dict[
            ir.VariableDeclaration, List[ir.ContractDefinition]
        ] = {}

    def detect(self) -> List[DetectorResult]:
        detections = []

        base_proxy_contracts = set()
        for (contract, _) in self._proxy_detections:
            for c in contract.linearized_base_contracts:
                if c == contract:
                    continue
                base_proxy_contracts.add(c)

        proxy_detections = {}
        for (contract, det) in self._proxy_detections:
            if contract not in base_proxy_contracts:
                proxy_detections[contract] = det

        base_impl_contracts = set()
        for (contract, _) in self._implementation_slots_detections:
            for c in contract.linearized_base_contracts:
                if c == contract:
                    continue
                base_impl_contracts.add(c)

        checked_pairs = set()
        impl_detections_contracts = set()
        for (contract, det) in self._implementation_slots_detections:
            impl_slot = get_last_detection_node(det).parent
            if (
                contract not in self._proxy_associated_contracts
                and contract not in base_impl_contracts
                and impl_slot in self._implementation_slots
                and contract not in impl_detections_contracts
            ):
                for proxy_contract in self._implementation_slots[impl_slot]:
                    if (
                        proxy_contract,
                        contract,
                    ) in checked_pairs or proxy_contract not in proxy_detections:
                        continue
                    checked_pairs.add((proxy_contract, contract))
                    impl_det = Detection(
                        contract,
                        f"Detected implementation contract with slot used in proxy contract {proxy_contract.name}",
                        subdetections=(det,),
                        lsp_range=contract.name_location,
                    )

                    dets = detect_selector_clashes(
                        proxy_contract,
                        contract,
                        proxy_detections[proxy_contract],
                        impl_det,
                    )
                    if len(dets) > 0:
                        detections.extend(dets)
        return list(detections)

    def visit_contract_definition(self, node: ir.ContractDefinition):
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
                                    Detection(
                                        node,
                                        "Detected proxy contract",
                                        subdetections=tuple(dets),
                                        lsp_range=node.name_location,
                                    ),
                                )
                            )
                            for det in dets:
                                last_det_node = get_last_detection_node(det)
                                if (
                                    isinstance(
                                        last_det_node.parent, ir.VariableDeclaration
                                    )
                                    and last_det_node.parent is not None
                                ):
                                    if (
                                        last_det_node.parent
                                        not in self._implementation_slots
                                    ):
                                        self._implementation_slots[
                                            last_det_node.parent
                                        ] = []
                                    self._implementation_slots[
                                        last_det_node.parent
                                    ].append(node)
                                self._proxy_associated_contracts.add(node)
                                for bc in node.linearized_base_contracts:
                                    self._proxy_associated_contracts.add(bc)

        if node not in self._proxy_associated_contracts:
            for fn in node.functions:
                for det in detect_slot_usage(fn):
                    self._implementation_slots_detections.add((node, det))

    @detector.command(name="proxy-contract-selector-clashes")
    def cli(self):
        """
        Detects selector clashes in proxy and implementation contracts.
        Proxy contracts are detected based on fallback function and usage of slot variables and
        implementation contracts that use same slots as proxy contracts
        """
        pass
