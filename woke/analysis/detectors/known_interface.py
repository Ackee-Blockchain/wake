from collections import namedtuple
from typing import List, Set, Union

from woke.analysis.detectors import DetectorAbc, DetectorResult, detector
from woke.ast.enums import ContractKind
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.event_definition import EventDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.types import Address, Array, Bool, Bytes, Mapping, String, UInt

REPORT_MARGIN = 0.8

Interface = namedtuple("Interface", ["name", "functions", "events"])
Event = namedtuple("Event", ["name", "parameters"])

IERC20_INTERFACE_DEFINITION = Interface(
    "IERC20",
    {
        b"\x18\x16\x0d\xdd": [(UInt, "uint256")],  # totalSupply
        b"\x70\xa0\x82\x31": [(UInt, "uint256")],  # balanceOf
        b"\xa9\x05\x9c\xbb": [(Bool, "bool")],  # transfer
        b"\xdd\x62\xed\x3e": [(UInt, "uint256")],  # allowance
        b"\x09\x5e\xa7\xb3": [(Bool, "bool")],  # approve
        b"\x23\xb8\x72\xdd": [(Bool, "bool")],  # transferFrom
    },
    {
        b"\xdd\xf2\x52\xad\x1b\xe2\xc8\x9b\x69\xc2\xb0\x68\xfc\x37\x8d\xaa\x95\x2b\xa7\xf1\x63\xc4\xa1\x16\x28\xf5\x5a\x4d\xf5\x23\xb3\xef": Event(
            "Transfer", [(Address, "address"), (Address, "address"), (UInt, "uint256")]
        ),
        b"\x8c\x5b\xe1\xe5\xeb\xec\x7d\x5b\xd1\x4f\x71\x42\x7d\x1e\x84\xf3\xdd\x03\x14\xc0\xf7\xb2\x29\x1e\x5b\x20\x0a\xc8\xc7\xc3\xb9\x25": Event(
            "Approval", [(Address, "address"), (Address, "address"), (UInt, "uint256")]
        ),
    },
)

IERC721_INTERFACE_DEFINITION = Interface(
    "IERC721",
    {
        b"\x70\xa0\x82\x31": [(UInt, "uint256")],  # balanceOf
        b"\x63\x52\x21\x1e": [(Address, "address")],  # ownerOf
        b"\x42\x84\x2e\x0e": [],  # safeTransferFrom
        b"\xb8\x8d\x4f\xde": [],  # safeTransferFrom
        b"\x23\xb8\x72\xdd": [],  # transferFrom
        b"\x09\x5e\xa7\xb3": [],  # approve
        b"\x08\x18\x12\xfc": [(Address, "address")],  # getApproved
        b"\xa2\x2c\xb4\x65": [],  # setApprovalForAll
        b"\xe9\x85\xe9\xc5": [(Bool, "bool")],  # isApprovedForAll
    },
    {
        b"\xdd\xf2\x52\xad\x1b\xe2\xc8\x9b\x69\xc2\xb0\x68\xfc\x37\x8d\xaa\x95\x2b\xa7\xf1\x63\xc4\xa1\x16\x28\xf5\x5a\x4d\xf5\x23\xb3\xef": Event(
            "Transfer", [(Address, "address"), (Address, "address"), (UInt, "uint256")]
        ),
        b"\x8c\x5b\xe1\xe5\xeb\xec\x7d\x5b\xd1\x4f\x71\x42\x7d\x1e\x84\xf3\xdd\x03\x14\xc0\xf7\xb2\x29\x1e\x5b\x20\x0a\xc8\xc7\xc3\xb9\x25": Event(
            "Approval", [(Address, "address"), (Address, "address"), (UInt, "uint256")]
        ),
        b"\x17\x30\x7e\xab\x39\xab\x61\x07\xe8\x89\x98\x45\xad\x3d\x59\xbd\x96\x53\xf2\x00\xf2\x20\x92\x04\x89\xca\x2b\x59\x37\x69\x6c\x31": Event(
            "ApprovalForAll",
            [(Address, "address"), (Address, "address"), (Bool, "bool")],
        ),
    },
)

IERC1155_INTERFACE_DEFINITION = Interface(
    "IERC1155",
    {
        b"\xf2\x42\x43\x2a": [],  # safeTransferFrom
        b"\x2e\xb2\xc2\xd6": [],  # safeBatchTransferFrom
        b"\x00\xfd\xd5\x8e": [(UInt, "t_uint256")],  # balanceOf
        b"\x4e\x12\x73\xf4": [(Array, "uint256[]")],  # balanceOfBatch
        b"\xa2\x2c\xb4\x65": [],  # setApprovalForAll
        b"\xe9\x85\xe9\xc5": [(Bool, "bool")],  # isApprovedForAll
    },
    {
        b"\xc3\xd5\x81\x68\xc5\xae\x73\x97\x73\x1d\x06\x3d\x5b\xbf\x3d\x65\x78\x54\x42\x73\x43\xf4\xc0\x83\x24\x0f\x7a\xac\xaa\x2d\x0f\x62": Event(
            "TransferSingle",
            [
                (Address, "address"),
                (Address, "address"),
                (Address, "address"),
                (UInt, "uint256"),
                (UInt, "uint256"),
            ],
        ),
        b"\x4a\x39\xdc\x06\xd4\xc0\xdb\xc6\x4b\x70\xaf\x90\xfd\x69\x8a\x23\x3a\x51\x8a\xa5\xd0\x7e\x59\x5d\x98\x3b\x8c\x05\x26\xc8\xf7\xfb": Event(
            "TransferBatch",
            [
                (Address, "address"),
                (Address, "address"),
                (Address, "address"),
                (Array, "uint256[]"),
                (Array, "uint256[]"),
            ],
        ),
        b"\x17\x30\x7e\xab\x39\xab\x61\x07\xe8\x89\x98\x45\xad\x3d\x59\xbd\x96\x53\xf2\x00\xf2\x20\x92\x04\x89\xca\x2b\x59\x37\x69\x6c\x31": Event(
            "ApprovalForAll",
            [(Address, "address"), (Address, "address"), (Bool, "bool")],
        ),
        b"\x6b\xb7\xff\x70\x86\x19\xba\x06\x10\xcb\xa2\x95\xa5\x85\x92\xe0\x45\x1d\xee\x26\x22\x93\x8c\x87\x55\x66\x76\x88\xda\xf3\x52\x9b": Event(
            "URI", [(String, "string"), (UInt, "uint256")]
        ),
    },
)


def get_functions_by_selectors(
    contract: ContractDefinition,
    interface_selectors: List[bytes],
) -> List[Union[FunctionDefinition, VariableDeclaration]]:
    function_selectors = {}
    for parent_contract in contract.linearized_base_contracts:
        for fn in [
            f
            for f in parent_contract.functions + parent_contract.declared_variables
            if f.function_selector is not None
        ]:
            if (
                fn.function_selector not in interface_selectors
                or fn.function_selector in function_selectors
            ):
                continue
            function_selectors[fn.function_selector] = fn
    return list(function_selectors.values())


def compare_return_types(contract_ret_types, interface_ret_types):
    for i in range(len(contract_ret_types)):
        rt1 = contract_ret_types[i]
        while isinstance(rt1, Mapping):
            rt1 = rt1.value_type

        rt2, rt2_abi_type = interface_ret_types[i]
        if not isinstance(rt1, rt2) or str(rt1.abi_type()) != rt2_abi_type:
            return False
    return True


def get_events_by_selectors(
    contract: ContractDefinition,
    interface_selectors: List[bytes],
) -> List[EventDefinition]:
    event_selectors = {}
    for parent_contract in contract.linearized_base_contracts:
        for event in parent_contract.events:
            if (
                event.event_selector not in interface_selectors
                or event.event_selector in event_selectors
            ):
                continue
            event_selectors[event.event_selector] = event
    return list(event_selectors.values())


@detector(-1034, "known-interface")
class KnownInterfaceDetector(DetectorAbc):
    """
    Detects contracts that implement a known interface (ERC20, ERC721, ERC1155) and incorrect return
    values of their functions
    """

    _detections: Set[DetectorResult]

    def __init__(self):
        self._detections = set()

    def report(self) -> List[DetectorResult]:
        return list(self._detections)

    def detect_functions(self, node: ContractDefinition, interface: Interface) -> None:
        functions_defined = get_functions_by_selectors(
            node, list(interface.functions.keys())
        )

        if len(functions_defined) / len(interface.functions) < REPORT_MARGIN:
            return

        if len(functions_defined) == len(interface.functions):
            self._detections.add(
                DetectorResult(
                    node,
                    f"{interface.name} implementation contract with all functions defined",
                )
            )
        else:
            self._detections.add(
                DetectorResult(
                    node,
                    f"Possible {interface.name} implementation contract "
                    f"with {len(functions_defined)}/{len(interface.functions)} functions defined",
                )
            )
        self.detect_events_discrepancies(node, interface)

        for fn in functions_defined:
            if isinstance(fn, VariableDeclaration):
                ret_types = [fn.type_name.type]
            else:
                ret_types = [p.type_name.type for p in fn.return_parameters.parameters]

            if len(ret_types) == len(
                interface.functions[fn.function_selector]
            ) and compare_return_types(
                ret_types, interface.functions[fn.function_selector]
            ):
                continue

            self._detections.add(
                DetectorResult(
                    fn,
                    f"Function {fn.name} does not match return parameters of {interface.name} interface",
                )
            )

    def detect_events_discrepancies(
        self, node: ContractDefinition, interface: Interface
    ) -> None:
        events_defined = get_events_by_selectors(node, list(interface.events.keys()))
        undefined_events = [
            event
            for (selector, event) in interface.events.items()
            if selector not in [d.event_selector for d in events_defined]
        ]

        if len(undefined_events) > 0:
            self._detections.add(
                DetectorResult(
                    node,
                    f"Only {len(events_defined)}/{len(interface.events)} events defined in possible "
                    f"implementation of {interface.name}, [{', '.join([e.name for e in undefined_events])}] are missing",
                )
            )

        for ev in events_defined:
            if ev.anonymous:
                self._detections.add(
                    DetectorResult(
                        ev,
                        f"Event {ev.name} is anonymous in {interface.name} interface",
                    )
                )

    def visit_contract_definition(self, node: ContractDefinition):
        if node.abstract or node.kind in (ContractKind.LIBRARY, ContractKind.INTERFACE):
            return

        for interface in [
            IERC20_INTERFACE_DEFINITION,
            IERC721_INTERFACE_DEFINITION,
            IERC1155_INTERFACE_DEFINITION,
        ]:
            self.detect_functions(node, interface)
