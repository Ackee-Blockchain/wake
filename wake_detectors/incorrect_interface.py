from __future__ import annotations

from collections import namedtuple
from typing import Dict, List, Optional, Set, Tuple, Union

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

FunctionInfo = namedtuple(
    "FunctionInfo", ["name", "state_mutability", "return_parameters"]
)
EventInfo = namedtuple("EventInfo", ["name", "parameters"])


class IncorrectInterfaceDetector(Detector):
    erc20_functions = {
        b"\x18\x16\x0d\xdd": FunctionInfo(
            "totalSupply()", {"pure", "view"}, ["uint256"]
        ),
        b"\x70\xa0\x82\x31": FunctionInfo("balanceOf(address)", {"view"}, ["uint256"]),
        b"\xa9\x05\x9c\xbb": FunctionInfo("transfer(address,uint256)", None, ["bool"]),
        b"\xdd\x62\xed\x3e": FunctionInfo(
            "allowance(address,address)", {"view"}, ["uint256"]
        ),
        b"\x09\x5e\xa7\xb3": FunctionInfo("approve(address,uint256)", None, ["bool"]),
        b"\x23\xb8\x72\xdd": FunctionInfo(
            "transferFrom(address,address,uint256)", None, ["bool"]
        ),
    }
    erc20_events = {
        b"\xdd\xf2\x52\xad\x1b\xe2\xc8\x9b\x69\xc2\xb0\x68\xfc\x37\x8d\xaa\x95\x2b\xa7\xf1\x63\xc4\xa1\x16\x28\xf5\x5a\x4d\xf5\x23\xb3\xef": EventInfo(
            "Transfer(address,address,uint256)",
            [True, True, False],
        ),
        b"\x8c\x5b\xe1\xe5\xeb\xec\x7d\x5b\xd1\x4f\x71\x42\x7d\x1e\x84\xf3\xdd\x03\x14\xc0\xf7\xb2\x29\x1e\x5b\x20\x0a\xc8\xc7\xc3\xb9\x25": EventInfo(
            "Approval(address,address,uint256)",
            [True, True, False],
        ),
    }
    erc721_functions = {
        b"\x70\xa0\x82\x31": FunctionInfo("balanceOf(address)", {"view"}, ["uint256"]),
        b"\x63\x52\x21\x1e": FunctionInfo("ownerOf(uint256)", {"view"}, ["address"]),
        b"\x42\x84\x2e\x0e": FunctionInfo(
            "safeTransferFrom(address,address,uint256)", None, []
        ),
        b"\xb8\x8d\x4f\xde": FunctionInfo(
            "safeTransferFrom(address,address,uint256,bytes)", None, []
        ),
        b"\x23\xb8\x72\xdd": FunctionInfo(
            "transferFrom(address,address,uint256)", None, []
        ),
        b"\x09\x5e\xa7\xb3": FunctionInfo("approve(address,uint256)", None, []),
        b"\x08\x18\x12\xfc": FunctionInfo(
            "getApproved(uint256)", {"view"}, ["address"]
        ),
        b"\xa2\x2c\xb4\x65": FunctionInfo("setApprovalForAll(address,bool)", None, []),
        b"\xe9\x85\xe9\xc5": FunctionInfo(
            "isApprovedForAll(address,address)", {"view"}, ["bool"]
        ),
    }
    erc721_events = {
        b"\xdd\xf2\x52\xad\x1b\xe2\xc8\x9b\x69\xc2\xb0\x68\xfc\x37\x8d\xaa\x95\x2b\xa7\xf1\x63\xc4\xa1\x16\x28\xf5\x5a\x4d\xf5\x23\xb3\xef": EventInfo(
            "Transfer(address,address,uint256)",
            [True, True, True],
        ),
        b"\x8c\x5b\xe1\xe5\xeb\xec\x7d\x5b\xd1\x4f\x71\x42\x7d\x1e\x84\xf3\xdd\x03\x14\xc0\xf7\xb2\x29\x1e\x5b\x20\x0a\xc8\xc7\xc3\xb9\x25": EventInfo(
            "Approval(address,address,uint256)",
            [True, True, True],
        ),
        b"\x17\x30\x7e\xab\x39\xab\x61\x07\xe8\x89\x98\x45\xad\x3d\x59\xbd\x96\x53\xf2\x00\xf2\x20\x92\x04\x89\xca\x2b\x59\x37\x69\x6c\x31": EventInfo(
            "ApprovalForAll(address,address,bool)",
            [True, True, False],
        ),
    }
    erc1155_functions = {
        b"\xf2\x42\x43\x2a": FunctionInfo(
            "safeTransferFrom(address,address,uint256,uint256,bytes)", None, []
        ),
        b"\x2e\xb2\xc2\xd6": FunctionInfo(
            "safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)", None, []
        ),
        b"\x00\xfd\xd5\x8e": FunctionInfo(
            "balanceOf(address,uint256)", {"view"}, ["uint256"]
        ),
        b"\x4e\x12\x73\xf4": FunctionInfo(
            "balanceOfBatch(address[],uint256[])", {"view"}, ["uint256[]"]
        ),
        b"\xa2\x2c\xb4\x65": FunctionInfo("setApprovalForAll(address,bool)", None, []),
        b"\xe9\x85\xe9\xc5": FunctionInfo(
            "isApprovedForAll(address,address)", {"view"}, ["bool"]
        ),
    }
    erc1155_events = {
        b"\x17\x30\x7e\xab\x39\xab\x61\x07\xe8\x89\x98\x45\xad\x3d\x59\xbd\x96\x53\xf2\x00\xf2\x20\x92\x04\x89\xca\x2b\x59\x37\x69\x6c\x31": EventInfo(
            "ApprovalForAll(address,address,bool)",
            [True, True, False],
        ),
        b"\x6b\xb7\xff\x70\x86\x19\xba\x06\x10\xcb\xa2\x95\xa5\x85\x92\xe0\x45\x1d\xee\x26\x22\x93\x8c\x87\x55\x66\x76\x88\xda\xf3\x52\x9b": EventInfo(
            "URI(string,uint256)",
            [False, True],
        ),
        b"\xc3\xd5\x81\x68\xc5\xae\x73\x97\x73\x1d\x06\x3d\x5b\xbf\x3d\x65\x78\x54\x42\x73\x43\xf4\xc0\x83\x24\x0f\x7a\xac\xaa\x2d\x0f\x62": EventInfo(
            "TransferSingle(address,address,address,uint256,uint256)",
            [True, True, True, False, False],
        ),
        b"\x4a\x39\xdc\x06\xd4\xc0\xdb\xc6\x4b\x70\xaf\x90\xfd\x69\x8a\x23\x3a\x51\x8a\xa5\xd0\x7e\x59\x5d\x98\x3b\x8c\x05\x26\xc8\xf7\xfb": EventInfo(
            "TransferBatch(address,address,address,uint256[],uint256[])",
            [True, True, True, False, False],
        ),
    }

    _erc20_threshold: int
    _erc721_threshold: int
    _erc1155_threshold: int
    _detections: Set[DetectorResult]

    def __init__(self) -> None:
        self._detections = set()

    def detect(self) -> List[DetectorResult]:
        return list(self._detections)

    def _check_interface(
        self,
        name: str,
        contract: ir.ContractDefinition,
        functions: Dict[bytes, FunctionInfo],
        events: Dict[bytes, EventInfo],
        interface: Dict[
            bytes,
            Union[
                ir.FunctionDefinition,
                ir.EventDefinition,
                ir.ErrorDefinition,
                ir.VariableDeclaration,
            ],
        ],
    ):
        missing = []
        for event_selector in events:
            if event_selector not in interface:
                missing.append(f"event {events[event_selector].name}")
                continue

            event = interface[event_selector]
            assert isinstance(event, ir.EventDefinition)
            if event.anonymous:
                self._detections.add(
                    DetectorResult(
                        Detection(event, f"{name} event must not be anonymous"),
                        impact=DetectorImpact.LOW,
                        confidence=DetectorConfidence.HIGH,
                        uri=generate_detector_uri(
                            name="incorrect-interface",
                            version=self.extra["package_versions"]["eth-wake"],
                            anchor="anonymous-events",
                        ),
                    )
                )

            if len(event.parameters.parameters) != len(
                events[event_selector].parameters
            ):
                self._detections.add(
                    DetectorResult(
                        Detection(
                            event, f"{name} event has incorrect number of parameters"
                        ),
                        impact=DetectorImpact.LOW,
                        confidence=DetectorConfidence.HIGH,
                        uri=generate_detector_uri(
                            name="incorrect-interface",
                            version=self.extra["package_versions"]["eth-wake"],
                        ),
                    )
                )
            else:
                for param, indexed in zip(
                    event.parameters.parameters, events[event_selector].parameters
                ):
                    if param.indexed != indexed:
                        self._detections.add(
                            DetectorResult(
                                Detection(
                                    param,
                                    f"{name} event parameter {'has' if not indexed else 'does not have'} indexed flag set",
                                ),
                                impact=DetectorImpact.LOW,
                                confidence=DetectorConfidence.HIGH,
                                uri=generate_detector_uri(
                                    name="incorrect-interface",
                                    version=self.extra["package_versions"]["eth-wake"],
                                    anchor="indexed-event-parameters",
                                ),
                            )
                        )

        for function_selector in functions:
            if function_selector not in interface:
                missing.append(f"function {functions[function_selector].name}")
                continue

            function = interface[function_selector]
            if isinstance(function, ir.VariableDeclaration):
                if "view" not in functions[function_selector].state_mutability:
                    self._detections.add(
                        DetectorResult(
                            Detection(
                                function,
                                f"{name} state-changing function was expected instead of read-only variable getter",
                            ),
                            impact=DetectorImpact.LOW,
                            confidence=DetectorConfidence.HIGH,
                            uri=generate_detector_uri(
                                name="incorrect-interface",
                                version=self.extra["package_versions"]["eth-wake"],
                                anchor="incorrect-state-mutability",
                            ),
                        )
                    )

                if len(functions[function_selector].return_parameters) != 1:
                    self._detections.add(
                        DetectorResult(
                            Detection(
                                function,
                                f"{name} function has incorrect number of return parameters",
                            ),
                            impact=DetectorImpact.LOW,
                            confidence=DetectorConfidence.HIGH,
                            uri=generate_detector_uri(
                                name="incorrect-interface",
                                version=self.extra["package_versions"]["eth-wake"],
                                anchor="incorrect-return-type",
                            ),
                        )
                    )
                else:
                    t = function.type
                    while isinstance(t, (types.Array, types.Mapping)):
                        if isinstance(t, types.Array):
                            t = t.base_type
                        else:
                            t = t.value_type

                    if t.abi_type != functions[function_selector].return_parameters[0]:
                        self._detections.add(
                            DetectorResult(
                                Detection(
                                    function,
                                    f"{name} function return parameter has incorrect type, expected {functions[function_selector].return_parameters[0]}",
                                ),
                                impact=DetectorImpact.LOW,
                                confidence=DetectorConfidence.HIGH,
                                uri=generate_detector_uri(
                                    name="incorrect-interface",
                                    version=self.extra["package_versions"]["eth-wake"],
                                    anchor="incorrect-return-type",
                                ),
                            )
                        )
            else:
                assert isinstance(function, ir.FunctionDefinition)
                if functions[function_selector].state_mutability is not None:
                    if (
                        function.state_mutability
                        not in functions[function_selector].state_mutability
                    ):
                        self._detections.add(
                            DetectorResult(
                                Detection(
                                    function,
                                    f"{name} function has incorrect state mutability, expected one of {functions[function_selector].state_mutability}",
                                ),
                                impact=DetectorImpact.LOW,
                                confidence=DetectorConfidence.HIGH,
                                uri=generate_detector_uri(
                                    name="incorrect-interface",
                                    version=self.extra["package_versions"]["eth-wake"],
                                    anchor="incorrect-state-mutability",
                                ),
                            )
                        )

                if len(function.return_parameters.parameters) != len(
                    functions[function_selector].return_parameters
                ):
                    self._detections.add(
                        DetectorResult(
                            Detection(
                                function,
                                f"{name} function has incorrect number of return parameters",
                            ),
                            impact=DetectorImpact.LOW,
                            confidence=DetectorConfidence.HIGH,
                            uri=generate_detector_uri(
                                name="incorrect-interface",
                                version=self.extra["package_versions"]["eth-wake"],
                                anchor="incorrect-return-type",
                            ),
                        )
                    )
                else:
                    param: ir.VariableDeclaration
                    for param, abi_type in zip(
                        function.return_parameters.parameters,
                        functions[function_selector].return_parameters,
                    ):
                        if param.type.abi_type != abi_type:
                            self._detections.add(
                                DetectorResult(
                                    Detection(
                                        param,
                                        f"{name} function return parameter has incorrect type, expected {abi_type}",
                                    ),
                                    impact=DetectorImpact.LOW,
                                    confidence=DetectorConfidence.HIGH,
                                    uri=generate_detector_uri(
                                        name="incorrect-interface",
                                        version=self.extra["package_versions"][
                                            "eth-wake"
                                        ],
                                        anchor="incorrect-return-type",
                                    ),
                                )
                            )

        if len(missing) > 0:
            # only one of TransferSingle/TransferBatch is required
            if (
                name == "ERC-1155"
                and len(missing) == 1
                and missing[0]
                in {
                    "event TransferSingle(address,address,address,uint256,uint256)",
                    "event TransferBatch(address,address,address,uint256[],uint256[])",
                }
            ):
                return

            self._detections.add(
                DetectorResult(
                    Detection(
                        contract,
                        f"{name} contract does not implement all functions/events. Missing: {', '.join(missing)}",
                    ),
                    impact=DetectorImpact.LOW,
                    confidence=DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="incorrect-interface",
                        version=self.extra["package_versions"]["eth-wake"],
                        anchor="missing-functions-events",
                    ),
                )
            )

    def visit_contract_definition(self, node: ir.ContractDefinition):
        from wake.analysis.interface import find_interface

        if node.abstract or node.kind in {
            ir.enums.ContractKind.INTERFACE,
            ir.enums.ContractKind.LIBRARY,
        }:
            return

        erc1155 = find_interface(node, self.erc1155_functions, self.erc1155_events)
        if len(erc1155) >= self._erc1155_threshold:
            self._check_interface(
                "ERC-1155", node, self.erc1155_functions, self.erc1155_events, erc1155
            )
            return

        erc721 = find_interface(node, self.erc721_functions, self.erc721_events)
        if len(erc721) >= self._erc721_threshold:
            self._check_interface(
                "ERC-721", node, self.erc721_functions, self.erc721_events, erc721
            )
            return

        erc20 = find_interface(node, self.erc20_functions, self.erc20_events)
        if len(erc20) >= self._erc20_threshold:
            self._check_interface(
                "ERC-20", node, self.erc20_functions, self.erc20_events, erc20
            )

    @detector.command(name="incorrect-interface")
    @click.option(
        "--erc20-threshold",
        type=click.IntRange(1, len(erc20_functions) + len(erc20_events)),
        default=4,
        help="Number of ERC-20 functions/events required to consider a contract an ERC-20 token",
    )
    @click.option(
        "--erc721-threshold",
        type=click.IntRange(1, len(erc721_functions) + len(erc721_events)),
        default=6,
        help="Number of ERC-721 functions/events required to consider a contract an ERC-721 token",
    )
    @click.option(
        "--erc1155-threshold",
        type=click.IntRange(1, len(erc1155_functions) + len(erc1155_events)),
        default=4,
        help="Number of ERC-1155 functions/events required to consider a contract an ERC-1155 token",
    )
    def cli(
        self, erc20_threshold: int, erc721_threshold: int, erc1155_threshold: int
    ) -> None:
        """
        Incorrectly implemented ERC-20/ERC-721/ERC-1155 interface
        """
        self._erc20_threshold = erc20_threshold
        self._erc721_threshold = erc721_threshold
        self._erc1155_threshold = erc1155_threshold
