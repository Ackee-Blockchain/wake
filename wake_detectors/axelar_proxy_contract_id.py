from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional, Set, Union

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


class AxelarProxyContractIdDetector(Detector):
    proxies: Dict[bytes, Set[ir.FunctionDefinition]]
    upgradeables: Dict[bytes, Set[ir.FunctionDefinition]]

    def __init__(self):
        self.proxies = {}
        self.upgradeables = {}

    @detector.command("axelar-proxy-contract-id")
    def cli(self):
        """
        Incorrect use of the `contractId` function in Axelar proxy and upgradeable contracts.
        """

    def detect(self) -> List[DetectorResult]:
        proxy_contracts: Dict[bytes, Set[ir.ContractDefinition]] = {}
        for selector, fns in self.proxies.items():
            proxy_contracts[selector] = set()
            visited: Set[
                ir.ContractDefinition
            ] = set(  # pyright: ignore reportGeneralTypeIssues
                fn.parent for fn in fns
            )
            queue: Deque[
                ir.ContractDefinition
            ] = deque(  # pyright: ignore reportGeneralTypeIssues
                fn.parent for fn in fns
            )

            while len(queue) > 0:
                contract = queue.popleft()
                if (
                    contract.kind == ir.enums.ContractKind.CONTRACT
                    and not contract.abstract
                ):
                    proxy_contracts[selector].add(contract)
                for child in contract.child_contracts:
                    if child not in visited and (
                        len(child.functions) == 0
                        or not any(fn.name == "contractId" for fn in child.functions)
                    ):
                        visited.add(child)
                        queue.append(child)

        upgradeable_contracts: Dict[bytes, Set[ir.ContractDefinition]] = {}
        for selector, fns in self.upgradeables.items():
            upgradeable_contracts[selector] = set()
            visited: Set[
                ir.ContractDefinition
            ] = set(  # pyright: ignore reportGeneralTypeIssues
                fn.parent for fn in fns
            )
            queue: Deque[
                ir.ContractDefinition
            ] = deque(  # pyright: ignore reportGeneralTypeIssues
                fn.parent for fn in fns
            )

            while len(queue) > 0:
                contract = queue.popleft()
                if (
                    contract.kind == ir.enums.ContractKind.CONTRACT
                    and not contract.abstract
                ):
                    upgradeable_contracts[selector].add(contract)
                for child in contract.child_contracts:
                    if child not in visited and (
                        len(child.functions) == 0
                        or not any(fn.name == "contractId" for fn in child.functions)
                    ):
                        visited.add(child)
                        queue.append(child)

        ret = []

        for proxies in sorted(proxy_contracts.values()):
            if len(proxies) > 1:
                sorted_proxies = sorted(proxies, key=lambda c: c.name)
                ret.append(
                    Detection(
                        sorted_proxies[0],
                        "Proxy contract ID shared between multiple contracts",
                        tuple(
                            Detection(
                                other, "Other contract", lsp_range=other.name_location
                            )
                            for other in sorted_proxies[1:]
                        ),
                        lsp_range=sorted_proxies[0].name_location,
                    )
                )

        for only_proxy in sorted(proxy_contracts.keys() - upgradeable_contracts.keys()):
            for proxy in sorted(proxy_contracts[only_proxy], key=lambda c: c.name):
                ret.append(
                    Detection(
                        proxy,
                        "Proxy contract without upgradeable contract with the same contract ID",
                        lsp_range=proxy.name_location,
                    )
                )
        for only_upgradeable in sorted(
            upgradeable_contracts.keys() - proxy_contracts.keys()
        ):
            for upgradeable in sorted(
                upgradeable_contracts[only_upgradeable], key=lambda c: c.name
            ):
                ret.append(
                    Detection(
                        upgradeable,
                        "Upgradeable contract without proxy contract with the same contract ID",
                        lsp_range=upgradeable.name_location,
                    )
                )

        whitelisted_functions = {
            bytes.fromhex("5c60da1b"): "implementation",
            bytes.fromhex("9ded06df"): "setup",
        }

        for common_contract_id in sorted(
            proxy_contracts.keys() & upgradeable_contracts.keys()
        ):
            for proxy in sorted(
                proxy_contracts[common_contract_id], key=lambda c: c.name
            ):
                for upgradeable in sorted(
                    upgradeable_contracts[common_contract_id], key=lambda c: c.name
                ):
                    proxy_functions: Dict[bytes, ir.FunctionDefinition] = {}
                    upgradeable_functions: Dict[bytes, ir.FunctionDefinition] = {}

                    for contract in proxy.linearized_base_contracts:
                        for func in contract.functions:
                            if (
                                func.function_selector is not None
                                and func.function_selector not in proxy_functions
                            ):
                                proxy_functions[func.function_selector] = func

                    for contract in upgradeable.linearized_base_contracts:
                        for func in contract.functions:
                            if (
                                func.function_selector is not None
                                and func.function_selector not in upgradeable_functions
                            ):
                                upgradeable_functions[func.function_selector] = func

                    for common_selector in sorted(
                        proxy_functions.keys() & upgradeable_functions.keys()
                    ):
                        if common_selector in whitelisted_functions:
                            func_name = whitelisted_functions[common_selector]
                            if (
                                proxy_functions[common_selector].name == func_name
                                and upgradeable_functions[common_selector].name
                                == func_name
                            ):
                                continue
                        ret.append(
                            Detection(
                                proxy,
                                "Proxy contract and upgradeable contract with function selector collision",
                                (
                                    Detection(
                                        upgradeable,
                                        "Upgradeable contract",
                                        lsp_range=upgradeable.name_location,
                                    ),
                                    Detection(
                                        proxy_functions[common_selector],
                                        f"Proxy contract function (selector: {common_selector.hex()})",
                                        lsp_range=proxy_functions[
                                            common_selector
                                        ].name_location,
                                    ),
                                    Detection(
                                        upgradeable_functions[common_selector],
                                        f"Upgradeable contract function (selector: {common_selector.hex()})",
                                        lsp_range=upgradeable_functions[
                                            common_selector
                                        ].name_location,
                                    ),
                                ),
                                lsp_range=proxy.name_location,
                            )
                        )

        return [
            DetectorResult(
                d,
                impact=DetectorImpact.WARNING,
                confidence=DetectorConfidence.HIGH,
                uri=generate_detector_uri(
                    name="axelar-proxy-contract-id",
                    version=self.extra["package_versions"]["eth-wake"],
                ),
            )
            for d in ret
        ]

    def _eval_contract_id(self, expr: ir.ExpressionAbc) -> Optional[Union[bytes, int]]:
        from Crypto.Hash import keccak

        if isinstance(expr, ir.FunctionCall):
            if expr.kind == ir.enums.FunctionCallKind.TYPE_CONVERSION:
                arg = self._eval_contract_id(expr.arguments[0])
                if isinstance(expr.type, types.IntAbc):
                    if isinstance(arg, int):
                        return arg
                    elif isinstance(arg, bytes):
                        return int.from_bytes(arg, "big", signed=False)
                    else:
                        return None
                elif isinstance(expr.type, (types.Bytes, types.FixedBytes)):
                    if isinstance(arg, bytes):
                        return arg
                    elif isinstance(arg, int):
                        return arg.to_bytes(32, "big", signed=False)
                    else:
                        return None
            elif expr.function_called == ir.enums.GlobalSymbol.KECCAK256:
                arg = expr.arguments[0]
                if not isinstance(arg, ir.Literal) or not isinstance(
                    arg.type, types.StringLiteral
                ):
                    return None
                contract_id = arg.value
                if contract_id is None:
                    return None

                return keccak.new(
                    data=contract_id.encode("utf-8"), digest_bits=256
                ).digest()
        elif isinstance(expr, ir.Literal):
            if expr.kind == ir.enums.LiteralKind.HEX_STRING:
                return expr.hex_value
            elif expr.kind == ir.enums.LiteralKind.NUMBER and expr.value is not None:
                if expr.value.startswith("0x"):
                    str_val = expr.value[2:].replace("_", "")
                    try:
                        return int(str_val, 16)
                    except ValueError:
                        return None
                else:
                    try:
                        return int(expr.value.replace("_", ""))
                    except ValueError:
                        return None
            else:
                return None
        elif isinstance(expr, ir.BinaryOperation):
            left = self._eval_contract_id(expr.left_expression)
            right = self._eval_contract_id(expr.right_expression)
            if expr.operator == ir.enums.BinaryOpOperator.PLUS:
                if isinstance(left, int) and isinstance(right, int):
                    return left + right
                else:
                    return None
            elif expr.operator == ir.enums.BinaryOpOperator.MINUS:
                if isinstance(left, int) and isinstance(right, int):
                    return left - right
                else:
                    return None
            else:
                return None
        else:
            return None

    def visit_contract_definition(self, node: ir.ContractDefinition):
        contract_id_function: Optional[ir.FunctionDefinition] = None
        for func in node.functions:
            if (
                func.name == "contractId"
                and len(func.parameters.parameters) == 0
                and len(func.return_parameters.parameters) == 1
                and isinstance(
                    func.return_parameters.parameters[0].type, types.FixedBytes
                )
                and func.return_parameters.parameters[0].type.bytes_count == 32
                and func.implemented
            ):
                contract_id_function = func
                break
        if contract_id_function is None:
            return

        returns = []
        assert contract_id_function.body is not None

        for statement in contract_id_function.body.statements_iter():
            if isinstance(statement, ir.Return):
                returns.append(statement)

        if len(returns) > 1:
            return

        if len(returns) == 1 and returns[0].expression is not None:
            expr = returns[0].expression
        else:
            ret_var = contract_id_function.return_parameters.parameters[0]
            assignments = []

            for ref in ret_var.references:
                if isinstance(ref, ir.ExternalReference):
                    continue
                elif isinstance(ref, ir.IdentifierPathPart):
                    ref = ref.underlying_node
                assignment = ref
                while assignment is not None:
                    if isinstance(assignment, ir.Assignment):
                        break
                    assignment = assignment.parent
                if assignment is None:
                    continue

                if len(assignment.assigned_variables) != 1:
                    continue
                assigned_var = assignment.assigned_variables[0]
                if assigned_var is None or len(assigned_var) != 1:
                    continue
                path = next(iter(assigned_var))
                if ret_var in path:
                    assignments.append(assignment)

            if len(assignments) != 1:
                return
            expr = assignments[0].right_expression

        contract_id = self._eval_contract_id(expr)
        if contract_id is None or contract_id in (0, b"\x00" * 32):
            return
        elif isinstance(contract_id, bytes) and len(contract_id) != 32:
            contract_id = bytes(32 - len(contract_id)) + contract_id
        elif isinstance(contract_id, int):
            contract_id = contract_id.to_bytes(32, "big", signed=False)

        if contract_id_function.visibility == ir.enums.Visibility.INTERNAL:
            if contract_id not in self.proxies:
                self.proxies[contract_id] = set()
            self.proxies[contract_id].add(contract_id_function)
        else:
            if contract_id not in self.upgradeables:
                self.upgradeables[contract_id] = set()
            self.upgradeables[contract_id].add(contract_id_function)
