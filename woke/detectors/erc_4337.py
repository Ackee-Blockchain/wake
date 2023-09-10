from __future__ import annotations

from typing import List, Set

import networkx as nx
import rich_click as click
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


class Erc4337Detector(Detector):
    SELECTORS = {
        bytes.fromhex("570e1a36"),  # createSender
        bytes.fromhex("3a871cdd"),  # validateUserOp
        bytes.fromhex("f465c77e"),  # validatePaymasterUserOp
    }

    _detections: List[DetectorResult]
    _target_functions: Set[ir.FunctionDefinition]
    _entry_points: Set[ir.ContractDefinition]
    _call_graph: nx.DiGraph

    def _process_expression(self, node: ir.ExpressionAbc) -> None:
        if len(self._target_functions) == 0 or not node.is_ref_to_state_variable:
            return
        if node.statement is None:
            return
        if not any(
            nx.has_path(self._call_graph, f, node.statement.declaration)
            for f in self._target_functions
        ):
            # storage reference not accessed by a restricted function
            return
        # TODO


    def detect(self) -> List[DetectorResult]:
        return self._detections
    
    def visit_function_definition(self, node: ir.FunctionDefinition):
        if (node.name in {"createSender", "validateUserOp", "validatePaymasterUserOp"} and node.function_selector not in self.SELECTORS
            or node.name == "simulateValidation" and node.function_selector != bytes.fromhex("ee219423")):
            self._detections.append(
                DetectorResult(
                    detection=Detection(
                        node,
                        f"ERC-4337: {node.name} function selector is incorrect",
                    ),
                    confidence=DetectionConfidence.MEDIUM,
                    impact=DetectionImpact.MEDIUM,
                )
            )
    
    def visit_new_expression(self, node: ir.NewExpression):
        if node.statement is None:
            return
        if isinstance(node.type_name.type, types.Contract) and any(
            nx.has_path(self._call_graph, f, node.statement.declaration)
            for f in self._target_functions
            if f.name in {"validateUserOp", "validatePaymasterUserOp"}
        ):
            self._detections.append(DetectorResult(
                Detection(
                    node,
                    f"ERC-4337: new contract is created in a restricted function",
                ),
                impact=DetectionImpact.HIGH,
                confidence=DetectionConfidence.HIGH,
            ))

    def visit_function_call(self, node: ir.FunctionCall):
        self._process_expression(node)

        if isinstance(node.expression, ir.Identifier) and node.expression.referenced_declaration == ir.enums.GlobalSymbolsEnum.SELFDESTRUCT:
            if any(nx.has_path(self._call_graph, f, node.statement.declaration) for f in self._target_functions):
                self._detections.append(DetectorResult(
                    Detection(
                        node,
                        f"ERC-4337: selfdestruct is called in a restricted function",
                    ),
                    impact=DetectionImpact.HIGH,
                    confidence=DetectionConfidence.HIGH,
                ))

    def visit_identifier(self, node: ir.Identifier):
        self._process_expression(node)

        if node.referenced_declaration in {
            ir.enums.GlobalSymbolsEnum.BLOCKHASH,
            ir.enums.GlobalSymbolsEnum.NOW,
            ir.enums.GlobalSymbolsEnum.GASLEFT,
        } and any(nx.has_path(self._call_graph, f, node.statement.declaration) for f in self._target_functions):
            self._detections.append(DetectorResult(
                Detection(
                    node,
                    f"ERC-4337: {node.source} is accessed by a restricted function",
                ),
                impact=DetectionImpact.HIGH,
                confidence=DetectionConfidence.HIGH,
            ))

    def visit_member_access(self, node: ir.MemberAccess):
        self._process_expression(node)

        if node.referenced_declaration in {
            ir.enums.GlobalSymbolsEnum.TX_GASPRICE,
            ir.enums.GlobalSymbolsEnum.BLOCK_GASLIMIT,
            ir.enums.GlobalSymbolsEnum.BLOCK_DIFFICULTY,
            ir.enums.GlobalSymbolsEnum.BLOCK_PREVRANDAO,
            ir.enums.GlobalSymbolsEnum.BLOCK_TIMESTAMP,
            ir.enums.GlobalSymbolsEnum.BLOCK_BASEFEE,
            ir.enums.GlobalSymbolsEnum.BLOCK_NUMBER,
            ir.enums.GlobalSymbolsEnum.ADDRESS_BALANCE,
            ir.enums.GlobalSymbolsEnum.TX_ORIGIN,
            ir.enums.GlobalSymbolsEnum.BLOCK_COINBASE,
        } and any(nx.has_path(self._call_graph, f, node.statement.declaration) for f in self._target_functions):
            self._detections.append(DetectorResult(
                Detection(
                    node,
                    f"ERC-4337: {node.source} is accessed by a restricted function",
                ),
                impact=DetectionImpact.HIGH,
                confidence=DetectionConfidence.HIGH,
            ))
    
    def visit_yul_function_call(self, node: ir.YulFunctionCall):
        if node.function_name in {"sload", "sstore"}:
            pass  # TODO

        # check value of call/callcode is set to zero in restricted functions
        if node.function_name in {"call", "callcode"} and any(
            nx.has_path(self._call_graph, f, node.inline_assembly.declaration)
            for f in self._target_functions
        ):
            value = node.arguments[2]
            if isinstance(value, ir.YulLiteral):
                tmp: str = value.value if value.value is not None else value.hex_value
                val = int(tmp, 16) if tmp.startswith("0x") else int(tmp)
                if val == 0:
                    return
            self._detections.append(DetectorResult(
                Detection(
                    node,
                    f"ERC-4337: call value must be set to zero in restricted functions"
                ),
                impact=DetectionImpact.HIGH,
                confidence=DetectionConfidence.HIGH,
            ))
        
        # check gas is called only as the first argument of a call
        if node.function_name == "gas":
            parent = node.parent
            if isinstance(parent, ir.YulFunctionCall) and parent.function_name in {
                "call", "callcode", "delegatecall", "staticcall"
            } and parent.arguments[0] == node:
                return
            if not any(nx.has_path(self._call_graph, f, node.inline_assembly.declaration) for f in self._target_functions):
                return
            self._detections.append(DetectorResult(
                Detection(
                    node,
                    f"ERC-4337: GAS opcode must be used only with CALL, CALLCODE, DELEGATECALL, or STATICCALL",
                ),
                impact=DetectionImpact.HIGH,
                confidence=DetectionConfidence.HIGH,
            ))
        
        # create2 can only be called up to once to instantiate the sender
        if node.function_name == "create2" and any(
            nx.has_path(self._call_graph, f, node.inline_assembly.declaration)
            for f in self._target_functions
            if f.name in {"validateUserOp", "validatePaymasterUserOp"}
        ):
            # create2 certainly cannot be called in validateUserOp or validatePaymasterUserOp
            self._detections.append(DetectorResult(
                Detection(
                    node,
                    f"ERC-4337: CREATE2 opcode can only be used once to instantiate the sender",
                ),
                impact=DetectionImpact.HIGH,
                confidence=DetectionConfidence.HIGH,
            ))


        if node.function_name in {
            "balance",
            "selfbalance",
            "create",
            "selfdestruct",
            "basefee",
            "origin",
            "gasprice",
            "blockhash",
            "coinbase",
            "timestamp",
            "number",
            "difficulty",
            "prevrandao",
            "gaslimit",
        } and any(nx.has_path(self._call_graph, f, node.inline_assembly.declaration) for f in self._target_functions):
            self._detections.append(DetectorResult(
                Detection(
                    node,
                    f"ERC-4337: {node.function_name} is called in a restricted function"
                ),
                impact=DetectionImpact.HIGH,
                confidence=DetectionConfidence.HIGH,
            ))


    # TODO storage access
    # TODO call must not set value
    # TODO call cannot call entrypoint methods except for depositFor
    # TODO check account verifies msg.sender == entry_point?

    @detector.command(name="erc-4337")
    def cli(self) -> None:
        from collections import deque

        self._detections = []
        self._call_graph = self.build.call_graph.graph
        self._target_functions = {
            f for f in self._call_graph.nodes
            if isinstance(f, ir.FunctionDefinition) and f.function_selector in self.SELECTORS
        }
        self._entry_points = set()

        for f in self._call_graph.nodes:
            if not isinstance(f, ir.FunctionDefinition) or f.function_selector != bytes.fromhex("ee219423"):
                # not simulateValidation
                continue
            if not isinstance(f.parent, ir.ContractDefinition):
                continue
            self._entry_points.add(f.parent)

            # find all external calls from simulateValidation
            q = deque([f])
            visited = {f}
            while q:
                n = q.popleft()

                for _, out, data in self._call_graph.out_edges(n, data=True):
                    if data["external"]:
                        self._target_functions.add(out)
                    elif out not in visited:
                        q.append(out)
                        visited.add(out)
