from __future__ import annotations

import heapq
import keyword
import logging
import os
import re
import shutil
import string
from collections import defaultdict, deque
from copy import deepcopy
from operator import itemgetter
from pathlib import Path
from typing import (
    Any,
    DefaultDict,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)
from urllib.request import pathname2url

import eth_utils
import networkx as nx
from Crypto.Hash import BLAKE2b, keccak
from intervaltree import IntervalTree
from typing_extensions import Literal

import wake.ir.types as types
from wake.compiler import SolidityCompiler
from wake.config import WakeConfig
from wake.core import get_logger
from wake.ir import (
    ArrayTypeName,
    ContractDefinition,
    DeclarationAbc,
    EnumDefinition,
    ErrorDefinition,
    EventDefinition,
    FunctionCall,
    FunctionDefinition,
    Mapping,
    ParameterList,
    RevertStatement,
    SourceUnit,
    StructDefinition,
    TypeNameAbc,
    UserDefinedTypeName,
    VariableDeclaration,
)
from wake.ir.enums import ContractKind, FunctionKind, StateMutability, Visibility
from wake.ir.reference_resolver import ReferenceResolver
from wake.utils import get_package_version

from .constants import DEFAULT_IMPORTS, INIT_CONTENT, TAB_WIDTH

logger = get_logger(__name__)


# TODO ensure that making the path alphanum won't create collisions
def _make_path_alphanum(source_unit_name: str) -> str:
    filtered = "".join(
        filter(lambda ch: ch.isalnum() or ch == "/" or ch == "_", source_unit_name)
    )
    return "/".join(
        f"_{segment}" if segment.startswith(tuple(string.digits)) else segment
        for segment in filtered.split("/")
    )


def _binary_search(lines: List[Tuple[bytes, int]], x: int) -> int:
    l = 0
    r = len(lines)

    while l < r:
        mid = l + (r - l) // 2
        if lines[mid][1] < x + 1:
            l = mid + 1
        else:
            r = mid

    return l - 1


def _path_to_uri(path: Path) -> str:
    if os.name == "nt":
        return "file:" + pathname2url(str(path.resolve()))
    else:
        return "file://" + pathname2url(str(path.resolve()))


def _parse_opcodes(opcodes: str) -> List[Tuple[int, str, int, Optional[int]]]:
    pc_op_map = []
    opcodes_spl = opcodes.split(" ")

    pc = 0
    ignore = False

    for i, opcode in enumerate(opcodes_spl):
        if ignore:
            ignore = False
            continue

        if not opcode.startswith("PUSH") or opcode == "PUSH0":
            pc_op_map.append((pc, opcode, 1, None))
            pc += 1
        else:
            size = int(opcode[4:]) + 1
            pc_op_map.append((pc, opcode, size, int(opcodes_spl[i + 1], 16)))
            pc += size
            ignore = True
    return pc_op_map


def _parse_source_map(
    source_map: str,
    pc_op_map: List[Tuple[int, str, int, Optional[int]]],
) -> Dict[int, Tuple[int, int, int, Optional[str]]]:
    pc_map = {}
    last_data = [-1, -1, -1, None, None]

    for i, sm_item in enumerate(source_map.split(";")):
        pc, op, size, argument = pc_op_map[i]
        source_spl = sm_item.split(":")
        for x in range(len(source_spl)):
            if source_spl[x] == "":
                continue
            if x < 3:
                last_data[x] = int(source_spl[x])
            else:
                last_data[x] = source_spl[x]

        pc_map[pc] = (
            last_data[0],
            last_data[0] + last_data[1],
            last_data[2],
            last_data[3],
        )

    return pc_map


class TypeGenerator:
    LIBRARY_PLACEHOLDER_REGEX = re.compile(r"__\$[0-9a-fA-F]{34}\$__")

    __config: WakeConfig
    __return_tx_obj: bool
    # generated types for the given source unit
    __source_unit_types: str
    # set of contracts that were already generated in the given source unit
    # used to avoid generating the same contract multiple times, eg. when multiple contracts inherit from it
    __already_generated_contracts: Set[str]
    __source_units: Dict[Path, SourceUnit]
    __interval_trees: Dict[Path, IntervalTree]
    __reference_resolver: ReferenceResolver
    __imports: SourceUnitImports
    __name_sanitizer: NameSanitizer
    __current_source_unit: str
    __pytypes_dir: Path
    __sol_to_py_lookup: Dict[str, Tuple[str, str]]
    # set of function names which should be overloaded
    __func_to_overload: Set[str]
    __contracts_index: Dict[str, Any]
    __errors_index: Dict[bytes, Dict[str, Any]]
    __events_index: Dict[bytes, Dict[str, Any]]
    __user_defined_value_types_index: Dict[str, str]
    __contracts_by_metadata_index: Dict[bytes, str]
    __contracts_inheritance_index: Dict[str, Tuple[str, ...]]
    __contracts_revert_constructor_index: Dict[str, Set[int]]
    __contracts_revert_index: Dict[str, Set[int]]
    __creation_code_index: List[Tuple[Tuple[Tuple[int, bytes], ...], str]]
    __line_indexes: Dict[Path, List[Tuple[bytes, int]]]
    # source unit name -> other source unit names in the cycle
    __cyclic_source_units: DefaultDict[str, Set[str]]
    # used to generate ListN types for N > 32
    __fixed_size_arrays: Set[int]

    def __init__(self, config: WakeConfig, return_tx_obj: bool):
        self.__config = config
        self.__return_tx_obj = return_tx_obj
        self.__source_unit_types = ""
        self.__already_generated_contracts = set()
        self.__source_units = {}
        self.__interval_trees = {}
        self.__reference_resolver = ReferenceResolver()
        self.__imports = SourceUnitImports(self)
        self.__name_sanitizer = NameSanitizer()
        self.__current_source_unit = ""
        self.__pytypes_dir = config.project_root_path / "pytypes"
        self.__sol_to_py_lookup = {}
        self.__init_sol_to_py_types()
        self.__func_to_overload = set()
        self.__contracts_index = {}
        self.__errors_index = {}
        self.__events_index = {}
        self.__user_defined_value_types_index = {}
        self.__contracts_by_metadata_index = {}
        self.__contracts_inheritance_index = {}
        self.__contracts_revert_constructor_index = {}
        self.__contracts_revert_index = {}
        self.__creation_code_index = []
        self.__line_indexes = {}
        self.__cyclic_source_units = defaultdict(set)
        self.__fixed_size_arrays = set()

        # built-in Error(str) and Panic(uint256) errors
        error_abi = {
            "name": "Error",
            "type": "error",
            "inputs": [{"internalType": "string", "name": "message", "type": "string"}],
        }
        panic_abi = {
            "name": "Panic",
            "type": "error",
            "inputs": [{"internalType": "uint256", "name": "code", "type": "uint256"}],
        }

        for item in [error_abi, panic_abi]:
            selector = eth_utils.abi.function_abi_to_4byte_selector(item)
            self.__errors_index[selector] = {}
            self.__errors_index[selector][""] = (
                "wake.development.transactions",
                (item["name"],),
            )

    def __setup_line_indexes(self, file: Path) -> None:
        content = self.__source_units[file].file_source
        tmp_lines = re.split(b"(\r?\n)", content)
        lines: List[bytes] = []
        for line in tmp_lines:
            if line in {b"\r\n", b"\n"}:
                lines[-1] += line
            else:
                lines.append(line)

        # UTF-8 encoded lines with prefix length
        encoded_lines: List[Tuple[bytes, int]] = []
        prefix_sum = 0
        for line in lines:
            encoded_lines.append((line, prefix_sum))
            prefix_sum += len(line)
        self.__line_indexes[file] = encoded_lines

    def __get_line_pos_from_byte_offset(
        self, file: Path, byte_offset: int
    ) -> Tuple[int, int]:
        if file not in self.__line_indexes:
            self.__setup_line_indexes(file)

        encoded_lines = self.__line_indexes[file]
        line_num = _binary_search(encoded_lines, byte_offset)
        line_data, prefix_sum = encoded_lines[line_num]
        line_offset = byte_offset - prefix_sum
        return line_num, line_offset

    # TODO do some prettier init :)
    def __init_sol_to_py_types(self):
        self.__sol_to_py_lookup[types.Address.__name__] = (
            "Union[Account, Address]",
            "Address",
        )
        self.__sol_to_py_lookup[types.String.__name__] = ("str", "str")
        self.__sol_to_py_lookup[types.Bool.__name__] = ("bool", "bool")
        self.__sol_to_py_lookup[types.Bytes.__name__] = (
            "Union[bytearray, bytes]",
            "bytearray",
        )
        self.__sol_to_py_lookup[types.Function.__name__] = ("Callable", "Callable")

    @property
    def current_source_unit(self) -> str:
        return self.__current_source_unit

    @property
    def cyclic_source_units(self) -> Set[str]:
        return self.__cyclic_source_units[self.__current_source_unit]

    def add_str_to_types(
        self, num_of_indentation: int, string: str, num_of_newlines: int
    ):
        self.__source_unit_types += (
            num_of_indentation * TAB_WIDTH * " " + string + num_of_newlines * "\n"
        )

    def get_name(
        self, declaration: DeclarationAbc, *, force_simple: bool = False
    ) -> str:
        source_unit = declaration.parent

        if (
            not force_simple
            and isinstance(source_unit, SourceUnit)
            and source_unit.source_unit_name != self.current_source_unit
            and source_unit.source_unit_name in self.cyclic_source_units
        ):
            n = self.__name_sanitizer.sanitize_name(declaration)
            return f"{n}.{n}"
        return self.__name_sanitizer.sanitize_name(declaration)

    def generate_deploy_func(
        self, contract: ContractDefinition, libraries: Dict[bytes, Tuple[str, str]]
    ):
        def generate_docstring():
            if source_code_link is not None or len(param_names) > 0:
                self.add_str_to_types(2, '"""', 1)
                if source_code_link is not None:
                    self.add_str_to_types(
                        2, source_code_link, 1 if len(param_names) == 0 else 2
                    )
                if len(param_names) > 0:
                    self.add_str_to_types(2, "Args:", 1)
                    for param_name, param_type in param_names:
                        self.add_str_to_types(3, f"{param_name}: {param_type}", 1)
                self.add_str_to_types(2, '"""', 1)

        param_names = []
        params = []
        for fn in contract.functions:
            if fn.name == "constructor":
                param_names, params = self.generate_func_params(fn)
                break
        params_str = "".join(param + ", " for param in params)

        libraries_str = "".join(
            f", {l[0]}: Optional[Union[{l[1]}, Address]] = None"
            for l in libraries.values()
        )

        contract_name = self.get_name(contract)
        source_code_link = None
        for fn in contract.functions:
            if fn.kind == FunctionKind.CONSTRUCTOR:
                line, _ = self.__get_line_pos_from_byte_offset(
                    fn.source_unit.file, fn.byte_location[0]
                )
                source_code_link = (
                    f"[Source code]({_path_to_uri(fn.source_unit.file)}#{line + 1})"
                )
                break

        # generate @overload stubs
        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f"""def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, return_tx: Literal[False]{'' if self.__return_tx_obj else ' = False'}{libraries_str}, request_type: Literal["call"], chain: Optional[Chain] = None, gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> bytearray:""",
            1,
        )
        generate_docstring()
        self.add_str_to_types(2, "...", 2)

        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f"""def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, return_tx: Literal[False]{'' if self.__return_tx_obj else ' = False'}{libraries_str}, request_type: Literal["tx"] = "tx", chain: Optional[Chain] = None, gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> {contract_name}:""",
            1,
        )
        generate_docstring()
        self.add_str_to_types(2, "...", 2)

        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f"""def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, return_tx: Literal[False]{'' if self.__return_tx_obj else ' = False'}{libraries_str}, request_type: Literal["estimate"], chain: Optional[Chain] = None, gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> int:""",
            1,
        )
        generate_docstring()
        self.add_str_to_types(2, "...", 2)

        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f"""def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, return_tx: Literal[False]{'' if self.__return_tx_obj else ' = False'}{libraries_str}, request_type: Literal["access_list"], chain: Optional[Chain] = None, gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> Tuple[Dict[Address, List[int]], int]:""",
            1,
        )
        generate_docstring()
        self.add_str_to_types(2, "...", 2)

        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f"""def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, return_tx: Literal[True]{' = True' if self.__return_tx_obj else ''}{libraries_str}, request_type: Literal["tx"] = "tx", chain: Optional[Chain] = None, gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> TransactionAbc[{contract_name}]:""",
            1,
        )
        generate_docstring()
        self.add_str_to_types(2, "...", 2)

        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f'def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, return_tx: bool = {self.__return_tx_obj}{libraries_str}, request_type: RequestType = "tx", chain: Optional[Chain] = None, gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> Union[bytearray, {contract_name}, int, Tuple[Dict[Address, List[int]], int], TransactionAbc[{contract_name}]]:',
            1,
        )

        generate_docstring()

        if contract.kind in {ContractKind.CONTRACT, ContractKind.LIBRARY}:
            if not contract.abstract:
                libs_arg = (
                    "{"
                    + ", ".join(
                        f"{lib_id}: ({l[0]}, '{l[1]}')"
                        for lib_id, l in libraries.items()
                    )
                    + "}"
                )
                self.add_str_to_types(
                    2,
                    f"return cls._deploy(request_type, [{', '.join(map(itemgetter(0), param_names))}], return_tx, {contract_name}, from_, value, gas_limit, {libs_arg}, chain, gas_price, max_fee_per_gas, max_priority_fee_per_gas, access_list, type, block, confirmations)",
                    1,
                )
            else:
                self.add_str_to_types(
                    2, 'raise Exception("Cannot deploy abstract contract")', 1
                )
        else:
            self.add_str_to_types(2, 'raise Exception("Cannot deploy interface")', 1)

    def generate_creation_code_func(
        self, contract: ContractDefinition, libraries: Dict[bytes, Tuple[str, str]]
    ):
        libraries_arg = "".join(
            f", {l[0]}: Union[{l[1]}, Address]" for l in libraries.values()
        )

        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f"def get_creation_code(cls{libraries_arg}) -> bytes:",
            1,
        )

        if contract.kind in {ContractKind.CONTRACT, ContractKind.LIBRARY}:
            if not contract.abstract:
                libs_arg = (
                    "{"
                    + ", ".join(
                        f"{lib_id}: ({l[0]}, '{l[1]}')"
                        for lib_id, l in libraries.items()
                    )
                    + "}"
                )
                self.add_str_to_types(
                    2,
                    f"return cls._get_creation_code({libs_arg})",
                    1,
                )
            else:
                self.add_str_to_types(
                    2,
                    'raise Exception("Cannot get creation code of an abstract contract")',
                    1,
                )
        else:
            self.add_str_to_types(
                2, 'raise Exception("Cannot get creation code of an interface")', 1
            )

    def _process_opcodes_for_revert(
        self,
        contract: ContractDefinition,
        fqn: str,
        parsed_opcodes,
        pc_map,
        index: Dict[str, Set[int]],
    ) -> None:
        for pc, op, size, argument in parsed_opcodes:
            if op == "REVERT" and pc in pc_map:
                start, end, file_id, _ = pc_map[pc]
                if file_id == -1:
                    continue
                try:
                    path = self.__reference_resolver.resolve_source_file_id(
                        file_id, contract.source_unit.cu_hash
                    )
                except KeyError:
                    continue

                intervals = self.__interval_trees[path].envelop(start, end)
                nodes: List = sorted(
                    [interval.data for interval in intervals],
                    key=lambda n: n.ast_tree_depth,
                )

                if len(nodes) > 0:
                    node = nodes[0]
                    if isinstance(node, FunctionCall) and isinstance(
                        node.parent, RevertStatement
                    ):
                        func_called = node.function_called
                        assert isinstance(func_called, ErrorDefinition)

                        if fqn not in index:
                            index[fqn] = set()
                        index[fqn].add(pc)

    def generate_contract_template(
        self, contract: ContractDefinition, base_names: str
    ) -> None:
        if contract.kind == ContractKind.LIBRARY:
            self.add_str_to_types(
                0, "class " + self.get_name(contract) + "(Library):", 1
            )
        else:
            self.add_str_to_types(
                0, "class " + self.get_name(contract) + "(" + base_names + "):", 1
            )
        line, _ = self.__get_line_pos_from_byte_offset(
            contract.source_unit.file, contract.byte_location[0]
        )
        self.add_str_to_types(1, '"""', 1)
        self.add_str_to_types(
            1, f"[Source code]({_path_to_uri(contract.source_unit.file)}#{line + 1})", 1
        )
        self.add_str_to_types(1, '"""', 1)

        compilation_info = contract.compilation_info
        assert compilation_info is not None
        assert compilation_info.abi is not None
        assert compilation_info.evm is not None
        assert compilation_info.evm.bytecode is not None
        assert compilation_info.evm.bytecode.object is not None
        assert compilation_info.evm.bytecode.opcodes is not None
        assert compilation_info.evm.bytecode.source_map is not None
        assert compilation_info.evm.deployed_bytecode is not None
        assert compilation_info.evm.deployed_bytecode.object is not None
        assert compilation_info.evm.deployed_bytecode.opcodes is not None
        assert compilation_info.evm.deployed_bytecode.source_map is not None

        fqn = f"{contract.parent.source_unit_name}:{contract.name}"

        for bytecode, index in [
            (compilation_info.evm.bytecode, self.__contracts_revert_constructor_index),
            (compilation_info.evm.deployed_bytecode, self.__contracts_revert_index),
        ]:
            parsed_opcodes = _parse_opcodes(bytecode.opcodes)
            pc_map = _parse_source_map(bytecode.source_map, parsed_opcodes)
            self._process_opcodes_for_revert(
                contract,
                fqn,
                parsed_opcodes,
                pc_map,
                index,
            )

        if len(compilation_info.evm.deployed_bytecode.object) > 0:
            metadata = bytes.fromhex(
                compilation_info.evm.deployed_bytecode.object[-106:]
            )
            assert len(metadata) == 53
            assert metadata not in self.__contracts_by_metadata_index
            self.__contracts_by_metadata_index[metadata] = fqn

        assert (
            fqn not in self.__contracts_inheritance_index
        ), f"Generating contract {fqn} twice"
        self.__contracts_inheritance_index[fqn] = tuple(
            f"{base.parent.source_unit_name}:{base.name}"
            for base in contract.linearized_base_contracts
        )

        abi_by_selector: Dict[
            Union[
                bytes, Literal["constructor"], Literal["fallback"], Literal["receive"]
            ],
            Dict,
        ] = {}

        module_name = "pytypes." + _make_path_alphanum(
            contract.parent.source_unit_name[:-3]
        ).replace("/", ".")

        for item in compilation_info.abi:
            if item["type"] == "function":
                if contract.kind == ContractKind.LIBRARY:
                    item_copy = deepcopy(item)
                    for arg in item_copy["inputs"]:
                        if arg["internalType"].startswith("contract "):
                            arg["internalType"] = arg["internalType"][9:]
                        elif arg["internalType"].startswith("struct "):
                            arg["internalType"] = arg["internalType"][7:]
                        elif arg["internalType"].startswith("enum "):
                            arg["internalType"] = arg["internalType"][5:]

                    selector = keccak.new(
                        data=f"{item['name']}({','.join(arg['internalType'] for arg in item_copy['inputs'])})".encode(
                            "utf-8"
                        ),
                        digest_bits=256,
                    ).digest()[:4]
                else:
                    selector = eth_utils.abi.function_abi_to_4byte_selector(item)
                abi_by_selector[selector] = item
            elif item["type"] == "error":
                selector = eth_utils.abi.function_abi_to_4byte_selector(item)
                abi_by_selector[selector] = item

                if selector not in self.__errors_index:
                    self.__errors_index[selector] = {}

                # find where the error is declared
                error_decl = None
                for error in contract.used_errors:
                    if error.name == item["name"]:
                        error_decl = error
                        break
                assert error_decl is not None

                if isinstance(error_decl.parent, ContractDefinition):
                    # error is declared in a contract
                    error_module_name = "pytypes." + _make_path_alphanum(
                        error_decl.parent.parent.source_unit_name[:-3]
                    ).replace("/", ".")
                    self.__errors_index[selector][fqn] = (
                        error_module_name,
                        (self.get_name(error_decl.parent), self.get_name(error_decl)),
                    )
                elif isinstance(error_decl.parent, SourceUnit):
                    error_module_name = "pytypes." + _make_path_alphanum(
                        error_decl.parent.source_unit_name[:-3]
                    ).replace("/", ".")
                    self.__errors_index[selector][fqn] = (
                        error_module_name,
                        (self.get_name(error_decl),),
                    )
                else:
                    raise Exception("Unknown error parent")
            elif item["type"] == "event":
                selector = eth_utils.abi.event_abi_to_log_topic(item)
                abi_by_selector[selector] = item

                event_decl = None
                for event in contract.used_events:
                    if event.event_selector == selector:
                        event_decl = event
                        break
                if event_decl is None:
                    continue

                if selector not in self.__events_index:
                    self.__events_index[selector] = {}

                # TODO: a contract may use two different events with the same selector when emitting events declared in other contracts
                if isinstance(event_decl.parent, ContractDefinition):
                    # event is declared in a contract
                    event_module_name = "pytypes." + _make_path_alphanum(
                        event_decl.parent.parent.source_unit_name[:-3]
                    ).replace("/", ".")
                    self.__events_index[selector][fqn] = (
                        event_module_name,
                        (self.get_name(event_decl.parent), self.get_name(event_decl)),
                    )
                elif isinstance(event_decl.parent, SourceUnit):
                    event_module_name = "pytypes." + _make_path_alphanum(
                        event_decl.parent.source_unit_name[:-3]
                    ).replace("/", ".")
                    self.__events_index[selector][fqn] = (
                        event_module_name,
                        (self.get_name(event_decl),),
                    )
                else:
                    raise Exception("Unknown event parent")
            elif item["type"] in {"constructor", "fallback", "receive"}:
                abi_by_selector[item["type"]] = item
            else:
                raise Exception(f"Unexpected ABI item type: {item['type']}")
        self.add_str_to_types(1, f"_abi = {abi_by_selector}", 1)

        if compilation_info.storage_layout is not None:
            self.add_str_to_types(
                1,
                f"_storage_layout = {compilation_info.storage_layout.json(by_alias=True, exclude_none=True)}",
                1,
            )

        self.add_str_to_types(
            1, f'_creation_code = "{compilation_info.evm.bytecode.object}"', 2
        )

        if contract.kind == ContractKind.LIBRARY:
            lib_id = keccak.new(data=fqn.encode("utf-8"), digest_bits=256).digest()[:17]
            self.add_str_to_types(1, f"_library_id = {lib_id}", 2)

        # find all needed libraries
        lib_ids: Set[bytes] = set()
        bytecode = compilation_info.evm.bytecode.object

        if len(bytecode) > 0:
            bytecode_segments: List[Tuple[int, bytes]] = []
            start = 0

            # TODO test segments work in this case
            for match in self.__class__.LIBRARY_PLACEHOLDER_REGEX.finditer(bytecode):
                s = match.start()
                e = match.end()
                segment = bytes.fromhex(bytecode[start:s])
                h = BLAKE2b.new(data=segment, digest_bits=256).digest()
                bytecode_segments.append((len(segment), h))
                start = e
                lib_id = bytes.fromhex(bytecode[s + 3 : e - 3])
                lib_ids.add(lib_id)

            fqn = f"{contract.parent.source_unit_name}:{contract.name}"

            segment = bytes.fromhex(bytecode[start:])
            h = BLAKE2b.new(data=segment, digest_bits=256).digest()
            bytecode_segments.append((len(segment), h))

            self.__creation_code_index.append((tuple(bytecode_segments), fqn))

        libraries: Dict[bytes, Tuple[str, str]] = {}
        source_units_queue = deque([contract.parent])

        while len(source_units_queue) > 0 and len(lib_ids) > 0:
            source_unit = source_units_queue.popleft()
            for c in source_unit.contracts:
                if c.kind == ContractKind.LIBRARY:
                    fqn = f"{c.parent.source_unit_name}:{c.name}"
                    lib_id = keccak.new(
                        data=fqn.encode("utf-8"), digest_bits=256
                    ).digest()[:17]

                    if lib_id in lib_ids:
                        lib_ids.remove(lib_id)
                        self.__imports.generate_contract_import(c)
                        libraries[lib_id] = (
                            c.name[0].lower() + c.name[1:],
                            self.get_name(c),
                        )

            source_units_queue.extend(
                imp.imported_source_unit for imp in source_unit.imports
            )

        assert len(lib_ids) == 0, "Not all libraries were found"

        self.generate_deploy_func(contract, libraries)
        self.add_str_to_types(0, "", 1)
        self.generate_creation_code_func(contract, libraries)
        self.add_str_to_types(0, "", 1)

    def generate_types_struct(
        self, structs: Iterable[StructDefinition], indent: int
    ) -> None:
        for struct in structs:
            members: List[Tuple[str, str, str, str]] = []
            for member in struct.members:
                member_name = self.get_name(member)
                member_type = self.parse_type_and_import(member.type, True)
                member_type_desc = member.type_string
                members.append(
                    (member_name, member_type, member_type_desc, member.name)
                )

            self.add_str_to_types(indent, "@dataclasses.dataclass", 1)
            self.add_str_to_types(indent, f"class {self.get_name(struct)}:", 1)
            self.add_str_to_types(indent + 1, '"""', 1)
            line, _ = self.__get_line_pos_from_byte_offset(
                struct.source_unit.file, struct.byte_location[0]
            )
            self.add_str_to_types(
                indent + 1,
                f"[Source code]({_path_to_uri(struct.source_unit.file)}#{line + 1})",
                2,
            )
            self.add_str_to_types(indent + 1, "Attributes:", 1)
            for member_name, member_type, member_type_desc, _ in members:
                self.add_str_to_types(
                    indent + 2, f"{member_name} ({member_type}): {member_type_desc}", 1
                )
            self.add_str_to_types(indent + 1, '"""', 1)
            self.add_str_to_types(indent + 1, f"original_name = '{struct.name}'", 2)

            for member_name, member_type, _, original_name in members:
                if member_name == original_name:
                    self.add_str_to_types(
                        indent + 1, f"{member_name}: {member_type}", 1
                    )
                else:
                    self.add_str_to_types(
                        indent + 1,
                        f'{member_name}: {member_type} = dataclasses.field(metadata={{"original_name": "{original_name}"}})',
                        1,
                    )
            self.add_str_to_types(0, "", 2)

    def generate_types_enum(self, enums: Iterable[EnumDefinition], indent: int) -> None:
        self.__imports.add_python_import("from enum import IntEnum")
        for enum in enums:
            self.add_str_to_types(indent, f"class {self.get_name(enum)}(IntEnum):", 1)
            line, _ = self.__get_line_pos_from_byte_offset(
                enum.source_unit.file, enum.byte_location[0]
            )
            self.add_str_to_types(indent + 1, '"""', 1)
            self.add_str_to_types(
                indent + 1,
                f"[Source code]({_path_to_uri(enum.source_unit.file)}#{line + 1})",
                2,
            )
            self.add_str_to_types(indent + 1, '"""', 1)
            num = 0
            for member in enum.values:
                self.add_str_to_types(
                    indent + 1, self.get_name(member) + " = " + str(num), 1
                )
                num += 1
            self.add_str_to_types(0, "", 2)

    def generate_types_error(
        self,
        errors: Iterable[ErrorDefinition],
        indent: int,
    ) -> None:
        for error in errors:
            # cannot generate pytypes for unused errors
            if len(error.used_in) == 0:
                continue

            used_in = next(iter(error.used_in))
            assert used_in.compilation_info is not None
            assert used_in.compilation_info.abi is not None

            error_abi = None

            for item in used_in.compilation_info.abi:
                if item["type"] == "error" and item["name"] == error.name:
                    selector = eth_utils.abi.function_abi_to_4byte_selector(item)
                    if selector == error.error_selector:
                        error_abi = item
                        break

            assert error_abi is not None

            parameters: List[Tuple[str, str, str, str]] = []
            unnamed_params_index = 1
            for parameter in error.parameters.parameters:
                if parameter.name:
                    parameter_name = self.get_name(parameter)
                else:
                    parameter_name = f"param{unnamed_params_index}"
                    unnamed_params_index += 1
                parameter_type = self.parse_type_and_import(parameter.type, True)
                parameter_type_desc = parameter.type_string
                parameters.append(
                    (
                        parameter_name,
                        parameter_type,
                        parameter_type_desc,
                        parameter.name,
                    )
                )

            self.add_str_to_types(indent, "@dataclasses.dataclass", 1)
            self.add_str_to_types(
                indent,
                f"class {self.get_name(error)}(TransactionRevertedError):",
                1,
            )

            line, _ = self.__get_line_pos_from_byte_offset(
                error.source_unit.file, error.byte_location[0]
            )
            self.add_str_to_types(indent + 1, '"""', 1)
            self.add_str_to_types(
                indent + 1,
                f"[Source code]({_path_to_uri(error.source_unit.file)}#{line + 1})",
                1 if len(parameters) == 0 else 2,
            )

            if len(parameters) > 0:
                self.add_str_to_types(indent + 1, "Attributes:", 1)
                for param_name, param_type, param_type_desc, _ in parameters:
                    self.add_str_to_types(
                        indent + 2, f"{param_name} ({param_type}): {param_type_desc}", 1
                    )

            self.add_str_to_types(indent + 1, '"""', 1)
            self.add_str_to_types(indent + 1, f"_abi = {error_abi}", 1)
            self.add_str_to_types(indent + 1, f"original_name = '{error.name}'", 1)
            self.add_str_to_types(indent + 1, f"selector = {error.error_selector}", 2)
            for param_name, param_type, _, original_name in parameters:
                if param_name == original_name:
                    self.add_str_to_types(indent + 1, f"{param_name}: {param_type}", 1)
                else:
                    self.add_str_to_types(
                        indent + 1,
                        f'{param_name}: {param_type} = dataclasses.field(metadata={{"original_name": "{original_name}"}})',
                        1,
                    )
            self.add_str_to_types(0, "", 2)

    def generate_types_event(
        self,
        events: Iterable[EventDefinition],
        indent: int,
    ) -> None:
        for event in events:
            # cannot generate pytypes for unused events
            if len(event.used_in) == 0:
                continue

            used_in = next(iter(event.used_in))
            assert used_in.compilation_info is not None
            assert used_in.compilation_info.abi is not None

            event_abi = None

            for item in used_in.compilation_info.abi:
                if item["type"] == "event" and item["name"] == event.name:
                    selector = eth_utils.abi.event_abi_to_log_topic(item)
                    if selector == event.event_selector:
                        event_abi = item
                        break

            assert event_abi is not None

            parameters: List[Tuple[str, str, str, str]] = []
            unnamed_params_index = 1
            for parameter in event.parameters.parameters:
                if parameter.name:
                    parameter_name = self.get_name(parameter)
                else:
                    parameter_name = f"param{unnamed_params_index}"
                    unnamed_params_index += 1

                if parameter.indexed and isinstance(
                    parameter.type,
                    (types.Array, types.Struct, types.Bytes, types.String),
                ):
                    parameter_name += "_hash"
                    parameter_type = "bytes"
                else:
                    parameter_type = self.parse_type_and_import(parameter.type, True)
                if parameter.indexed:
                    parameter_type_desc = "indexed " + parameter.type_string
                else:
                    parameter_type_desc = parameter.type_string
                parameters.append(
                    (
                        parameter_name,
                        parameter_type,
                        parameter_type_desc,
                        parameter.name,
                    )
                )

            self.add_str_to_types(indent, "@dataclasses.dataclass", 1)
            self.add_str_to_types(indent, f"class {self.get_name(event)}:", 1)

            line, _ = self.__get_line_pos_from_byte_offset(
                event.source_unit.file, event.byte_location[0]
            )
            self.add_str_to_types(indent + 1, '"""', 1)
            self.add_str_to_types(
                indent + 1,
                f"[Source code]({_path_to_uri(event.source_unit.file)}#{line + 1})",
                1 if len(parameters) == 0 else 2,
            )

            if len(parameters) > 0:
                self.add_str_to_types(indent + 1, "Attributes:", 1)
                for param_name, param_type, param_type_desc, _ in parameters:
                    self.add_str_to_types(
                        indent + 2, f"{param_name} ({param_type}): {param_type_desc}", 1
                    )

            self.add_str_to_types(indent + 1, '"""', 1)
            self.add_str_to_types(indent + 1, f"_abi = {event_abi}", 1)
            self.add_str_to_types(
                indent + 1,
                "origin: Account = dataclasses.field(init=False, compare=False, repr=False)",
                1,
            )
            self.add_str_to_types(indent + 1, f"original_name = '{event.name}'", 1)
            self.add_str_to_types(indent + 1, f"selector = {event.event_selector}", 2)
            for param_name, param_type, _, original_name in parameters:
                if param_name == original_name:
                    self.add_str_to_types(indent + 1, f"{param_name}: {param_type}", 1)
                else:
                    self.add_str_to_types(
                        indent + 1,
                        f'{param_name}: {param_type} = dataclasses.field(metadata={{"original_name": "{original_name}"}})',
                        1,
                    )
            self.add_str_to_types(0, "", 2)

    # parses the expr to string
    # optionaly generates an import
    def parse_type_and_import(self, expr: types.TypeAbc, return_types: bool) -> str:
        if return_types:
            types_index = 1
        else:
            types_index = 0

        if isinstance(expr, types.Struct):
            parent = expr.ir_node.parent
            if isinstance(parent, ContractDefinition):
                self.__imports.generate_contract_import(parent)
                return f"{self.get_name(parent)}.{self.get_name(expr.ir_node)}"
            else:
                self.__imports.generate_struct_import(expr)
                return self.get_name(expr.ir_node)
        elif isinstance(expr, types.Enum):
            parent = expr.ir_node.parent
            if isinstance(parent, ContractDefinition):
                self.__imports.generate_contract_import(parent)
                return f"{self.get_name(parent)}.{self.get_name(expr.ir_node)}"
            else:
                self.__imports.generate_enum_import(expr)
                return self.get_name(expr.ir_node)
        elif isinstance(expr, types.UserDefinedValueType):
            return self.parse_type_and_import(
                expr.ir_node.underlying_type.type, return_types
            )
        elif isinstance(expr, types.Array):
            if expr.length is None:
                return (
                    f"List[{self.parse_type_and_import(expr.base_type, return_types)}]"
                )
            elif expr.length <= 32:
                return f"List{expr.length}[{self.parse_type_and_import(expr.base_type, return_types)}]"
            else:
                self.__fixed_size_arrays.add(expr.length)
                return f"List{expr.length}[{self.parse_type_and_import(expr.base_type, return_types)}]"
        elif isinstance(expr, types.Contract):
            self.__imports.generate_contract_import(expr.ir_node)
            return self.get_name(expr.ir_node)
        elif isinstance(expr, types.FixedBytes):
            return f"bytes{expr.bytes_count}"
        elif isinstance(expr, types.Int):
            return f"int{expr.bits_count}"
        elif isinstance(expr, types.UInt):
            return f"uint{expr.bits_count}"
        elif isinstance(expr, types.Mapping):
            return f"Dict[{self.parse_type_and_import(expr.key_type, return_types)}, {self.parse_type_and_import(expr.value_type, return_types)}]"
        else:
            return self.__sol_to_py_lookup[expr.__class__.__name__][types_index]

    def generate_func_params(
        self, fn: FunctionDefinition
    ) -> Tuple[List[Tuple[str, str]], List[str]]:
        params = []
        param_names = []
        unnamed_params_identifier: int = 1
        generated_names = {
            self.get_name(par) for par in fn.parameters.parameters if par.name != ""
        }

        for param in fn.parameters.parameters:
            if param.name == "":
                param_name: str = "arg" + str(unnamed_params_identifier)
                unnamed_params_identifier += 1
                while param_name in generated_names:
                    param_name += "_"
            else:
                param_name = self.get_name(param)
            param_names.append((param_name, param.type_string))
            params.append(
                f"{param_name}: {self.parse_type_and_import(param.type, False)}"
            )
        return param_names, params

    def generate_func_returns(self, fn: FunctionDefinition) -> List[Tuple[str, str]]:
        return [
            (self.parse_type_and_import(par.type, True), par.type_string)
            for par in fn.return_parameters.parameters
        ]

    def is_compound_type(self, var_type: types.TypeAbc):
        name = var_type.__class__.__name__
        return name == "Array" or name == "Mapping"

    def generate_getter_for_state_var(self, decl: VariableDeclaration):
        def get_struct_return_list(
            struct_type_name: UserDefinedTypeName,
        ) -> List[Tuple[str, str]]:
            struct = struct_type_name.type
            assert isinstance(struct, types.Struct)
            node = struct.ir_node
            non_excluded: List[Tuple[str, str]] = []
            for member in node.members:
                if not isinstance(member.type, types.Mapping) and not isinstance(
                    member.type, types.Array
                ):
                    non_excluded.append(
                        (
                            self.parse_type_and_import(member.type, True),
                            member.type_string,
                        )
                    )
            if len(node.members) == len(non_excluded):
                # nothing was excluded -> the whole struct will be used -> add the struct to imports
                parent = node.parent
                if isinstance(parent, ContractDefinition):
                    self.__imports.generate_contract_import(parent)
                    return [
                        (
                            f"{self.get_name(parent)}.{self.get_name(struct.ir_node)}",
                            struct_type_name.type_string,
                        )
                    ]
                else:
                    self.__imports.generate_struct_import(struct)
                    return [
                        (self.get_name(struct.ir_node), struct_type_name.type_string)
                    ]
            else:
                return non_excluded

        returns: List[Tuple[str, str]] = []
        param_names: List[Tuple[str, str]] = []
        # if the type is compound we need to use the type as an index, for primitive types we use the
        # the type only for the return
        # TODO reorder the elif chain such that the most common types are on the top
        def generate_getter_helper(
            var_type_name: TypeNameAbc, use_parse: bool, depth: int
        ) -> List[str]:
            nonlocal returns
            nonlocal param_names
            parsed = []
            var_type = var_type_name.type
            if isinstance(var_type, types.Struct):
                if depth == 0:
                    pass
                else:
                    parent = var_type.ir_node.parent
                    if isinstance(parent, ContractDefinition):
                        self.__imports.generate_contract_import(parent)
                        parsed.append(
                            f"{self.get_name(parent)}.{self.get_name(var_type.ir_node)}"
                        )
                    else:
                        self.__imports.generate_struct_import(var_type)
                        parsed.append(self.get_name(var_type.ir_node))
                assert isinstance(var_type_name, UserDefinedTypeName)
                returns = get_struct_return_list(var_type_name)
            elif isinstance(var_type, types.Enum):
                parent = var_type.ir_node.parent
                if isinstance(parent, ContractDefinition):
                    self.__imports.generate_contract_import(parent)
                    parsed.append(
                        f"{self.get_name(parent)}.{self.get_name(var_type.ir_node)}"
                    )
                    returns = [
                        (
                            f"{self.get_name(parent)}.{self.get_name(var_type.ir_node)}",
                            var_type_name.type_string,
                        )
                    ]

                else:
                    self.__imports.generate_enum_import(var_type)
                    parsed.append(self.get_name(var_type.ir_node))
                    returns = [
                        (self.get_name(var_type.ir_node), var_type_name.type_string)
                    ]
            elif isinstance(var_type, types.UserDefinedValueType):
                underlying_type = var_type.ir_node.underlying_type.type
                if isinstance(underlying_type, types.FixedBytes):
                    parsed.append(f"bytes{underlying_type.bytes_count}")
                    returns = [
                        (
                            f"bytes{underlying_type.bytes_count}",
                            var_type_name.type_string,
                        )
                    ]
                elif isinstance(underlying_type, types.Int):
                    parsed.append(f"int{underlying_type.bits_count}")
                    returns = [
                        (f"int{underlying_type.bits_count}", var_type_name.type_string)
                    ]
                elif isinstance(underlying_type, types.UInt):
                    parsed.append(f"uint{underlying_type.bits_count}")
                    returns = [
                        (f"uint{underlying_type.bits_count}", var_type_name.type_string)
                    ]
                else:
                    parsed.append(
                        self.__sol_to_py_lookup[underlying_type.__class__.__name__][0]
                    )
                    returns = [
                        (
                            self.__sol_to_py_lookup[underlying_type.__class__.__name__][
                                1
                            ],
                            var_type_name.type_string,
                        )
                    ]
            elif isinstance(var_type, types.Array):
                use_parse = True
                param_names.append(("index" + str(depth), "uint256"))
                parsed.append(f"index{depth}: int")
                assert isinstance(var_type_name, ArrayTypeName)
                if self.is_compound_type(var_type.base_type):
                    parsed.extend(
                        generate_getter_helper(var_type_name.base_type, True, depth + 1)
                    )
                else:
                    # ignores the parsed return, only called for the side-effect of changing the returns var to value_type
                    _ = generate_getter_helper(
                        var_type_name.base_type, False, depth + 1
                    )
            elif isinstance(var_type, types.Mapping):
                # parse key
                use_parse = True
                assert isinstance(var_type_name, Mapping)
                param_names.append(
                    ("key" + str(depth), var_type_name.key_type.type_string)
                )
                key_type = generate_getter_helper(
                    var_type_name.key_type, True, depth + 1
                )
                assert len(key_type) == 1
                parsed.append(f"key{depth}: {key_type[0]}")
                if self.is_compound_type(var_type.value_type):
                    parsed.extend(
                        generate_getter_helper(
                            var_type_name.value_type, True, depth + 1
                        )
                    )
                else:
                    # ignores the parsed return, only called for the side-effect of changing the returns var to value_type
                    _ = generate_getter_helper(
                        var_type_name.value_type, True, depth + 1
                    )
            elif isinstance(var_type, types.Contract):
                self.__imports.generate_contract_import(var_type.ir_node)
                parsed.append(self.get_name(var_type.ir_node))
                returns = [(self.get_name(var_type.ir_node), var_type_name.type_string)]
            elif isinstance(var_type, types.FixedBytes):
                parsed.append(f"bytes{var_type.bytes_count}")
                returns = [(f"bytes{var_type.bytes_count}", var_type_name.type_string)]
            elif isinstance(var_type, types.Int):
                parsed.append(f"int{var_type.bits_count}")
                returns = [(f"int{var_type.bits_count}", var_type_name.type_string)]
            elif isinstance(var_type, types.UInt):
                parsed.append(f"uint{var_type.bits_count}")
                returns = [(f"uint{var_type.bits_count}", var_type_name.type_string)]
            else:
                parsed.append(self.__sol_to_py_lookup[var_type.__class__.__name__][0])
                returns = [
                    (
                        self.__sol_to_py_lookup[var_type.__class__.__name__][1],
                        var_type_name.type_string,
                    )
                ]

            return parsed if use_parse else []

        generated_params = generate_getter_helper(decl.type_name, False, 0)

        if len(returns) == 0:
            returns_str = "None"
        elif len(returns) == 1:
            returns_str = returns[0][0]
        else:
            returns_str = f"Tuple[{', '.join(ret[0] for ret in returns)}]"

        self.generate_type_hint_stub_func(
            decl, generated_params, returns_str, "call", True, param_names, returns
        )
        self.generate_type_hint_stub_func(
            decl, generated_params, "int", "estimate", False, param_names, returns
        )
        self.generate_type_hint_stub_func(
            decl,
            generated_params,
            "Tuple[Dict[Address, List[int]], int]",
            "access_list",
            False,
            param_names,
            returns,
        )
        self.generate_type_hint_stub_func(
            decl,
            generated_params,
            f"TransactionAbc[{returns_str}]",
            "tx",
            False,
            param_names,
            returns,
        )

        self.generate_func_implementation(
            decl,
            generated_params,
            param_names,
            returns,
        )

    # receives names of params and their type hints, returns only the types to be used for dispatch
    def get_types_from_func_params(self, params) -> str:
        # 1. split on , to separete the params
        # 2. split on : and get the last (the second) elem to get the type (each pair is in the format name: type)
        # 3. remove the last elem which is params: Optional[TxParams] = None (not used for dispatch)
        name_type = params.split(",")
        types = []
        for name_type_pair in name_type:
            types.append(name_type_pair.split(":")[-1])
        res: str = ", ".join(types[:-1])
        if res:
            # remove the first char which a redundant whitespace
            res = res[1:]
        return res

    def generate_func_implementation(
        self,
        declaration: Union[FunctionDefinition, VariableDeclaration],
        params: List[str],
        param_names: List[Tuple[str, str]],
        returns: List[Tuple[str, str]],
    ):
        is_view_or_pure: bool = isinstance(
            declaration, VariableDeclaration
        ) or declaration.state_mutability in {
            StateMutability.VIEW,
            StateMutability.PURE,
        }
        params_str = "".join(param + ", " for param in params)
        if len(returns) == 0:
            returns_str = None
        elif len(returns) == 1:
            returns_str = returns[0][0]
        else:
            returns_str = f"Tuple[{', '.join(ret[0] for ret in returns)}]"
        self.add_str_to_types(
            1,
            f"""def {self.get_name(declaration)}(self, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, to: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, request_type: RequestType = '{'call' if is_view_or_pure else 'tx'}', gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> Union[{returns_str}, TransactionAbc[{returns_str}], int, Tuple[Dict[Address, List[int]], int]]:""",
            1,
        )

        line, _ = self.__get_line_pos_from_byte_offset(
            declaration.source_unit.file, declaration.byte_location[0]
        )
        self.add_str_to_types(2, '"""', 1)
        self.add_str_to_types(
            2,
            f"[Source code]({_path_to_uri(declaration.source_unit.file)}#{line + 1})",
            1 if len(param_names) + len(returns) == 0 else 2,
        )
        if len(param_names) > 0:
            self.add_str_to_types(2, "Args:", 1)
            for param_name, param_type in param_names:
                self.add_str_to_types(3, f"{param_name}: {param_type}", 1)
        if len(returns) == 1:
            self.add_str_to_types(2, "Returns:", 1)
            self.add_str_to_types(3, f"{returns[0][1]}", 1)
        elif len(returns) > 1:
            self.add_str_to_types(2, "Returns:", 1)
            self.add_str_to_types(3, f'({", ".join(ret[1] for ret in returns)})', 1)
        self.add_str_to_types(2, '"""', 1)

        if len(returns) == 0:
            return_types = "NoneType"
        elif len(returns) == 1:
            return_types = returns[0][0]
        else:
            return_types = f"Tuple[{', '.join(map(itemgetter(0), returns))}]"

        assert declaration.function_selector is not None
        fn_selector = declaration.function_selector.hex()
        self.add_str_to_types(
            2,
            f'return self._execute(self.chain, request_type, "{fn_selector}", [{", ".join(map(itemgetter(0), param_names))}], True if request_type == "tx" else False, {return_types}, from_, to if to is not None else str(self.address), value, gas_limit, gas_price, max_fee_per_gas, max_priority_fee_per_gas, access_list, type, block, confirmations)',
            2,
        )

    def generate_type_hint_stub_func(
        self,
        declaration: Union[FunctionDefinition, VariableDeclaration],
        params: List[str],
        returns_str: str,
        request_type: str,
        request_type_is_default: bool,
        param_names: List[Tuple[str, str]],
        returns: List[Tuple[str, str]],
    ):
        params_str = "".join(param + ", " for param in params)

        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(
            1,
            f"""def {self.get_name(declaration)}(self, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, to: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, request_type: Literal["{request_type}"]{' = "' + request_type + '"' if request_type_is_default else ''}, gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> {returns_str}:""",
            1,
        )
        line, _ = self.__get_line_pos_from_byte_offset(
            declaration.source_unit.file, declaration.byte_location[0]
        )
        self.add_str_to_types(2, '"""', 1)
        self.add_str_to_types(
            2,
            f"[Source code]({_path_to_uri(declaration.source_unit.file)}#{line + 1})",
            1 if len(param_names) + len(returns) == 0 else 2,
        )
        if len(param_names) > 0:
            self.add_str_to_types(2, "Args:", 1)
            for param_name, param_type in param_names:
                self.add_str_to_types(3, f"{param_name}: {param_type}", 1)
        if len(returns) == 1:
            self.add_str_to_types(2, "Returns:", 1)
            self.add_str_to_types(3, f"{returns[0][1]}", 1)
        elif len(returns) > 1:
            self.add_str_to_types(2, "Returns:", 1)
            self.add_str_to_types(3, f'({", ".join(ret[1] for ret in returns)})', 1)
        self.add_str_to_types(2, '"""', 1)
        self.add_str_to_types(2, "...", 2)

    def generate_types_function(self, fn: FunctionDefinition):
        params_names, params = self.generate_func_params(fn)
        returns = self.generate_func_returns(fn)

        if len(returns) == 0:
            returns_str = "None"
        elif len(returns) == 1:
            returns_str = returns[0][0]
        else:
            returns_str = f"Tuple[{', '.join(ret[0] for ret in returns)}]"

        is_pure_or_view = fn.state_mutability in {
            StateMutability.PURE,
            StateMutability.VIEW,
        }

        self.generate_type_hint_stub_func(
            fn,
            params,
            returns_str,
            "call",
            is_pure_or_view,
            params_names,
            returns,
        )
        self.generate_type_hint_stub_func(
            fn,
            params,
            "int",
            "estimate",
            False,
            params_names,
            returns,
        )
        self.generate_type_hint_stub_func(
            fn,
            params,
            "Tuple[Dict[Address, List[int]], int]",
            "access_list",
            False,
            params_names,
            returns,
        )
        self.generate_type_hint_stub_func(
            fn,
            params,
            f"TransactionAbc[{returns_str}]",
            "tx",
            not is_pure_or_view,
            params_names,
            returns,
        )

        assert fn.function_selector is not None
        self.generate_func_implementation(
            fn,
            params,
            params_names,
            returns,
        )

    def generate_types_contract(self, contract: ContractDefinition) -> None:
        fqn = f"{contract.parent.source_unit_name}:{contract.name}"
        if fqn in self.__already_generated_contracts:
            return
        else:
            self.__already_generated_contracts.add(fqn)

        base_names: List[str] = []

        for base in reversed(contract.base_contracts):
            parent_contract = base.base_name.referenced_declaration
            assert isinstance(parent_contract, ContractDefinition)
            # only the types for contracts in the same source_unit are generated
            if (
                parent_contract.parent.source_unit_name
                == contract.parent.source_unit_name
            ):
                base_names.append(self.get_name(parent_contract))
                self.generate_types_contract(parent_contract)
            # contract is not in the same source unit, so it must be imported
            else:
                base_names.append(self.get_name(parent_contract, force_simple=True))
                self.__imports.generate_contract_import(parent_contract, force=True)

        contract_module_name = "pytypes." + _make_path_alphanum(
            contract.parent.source_unit_name[:-3]
        ).replace("/", ".")
        self.__contracts_index[fqn] = (
            contract_module_name,
            (self.get_name(contract),),
        )

        if len(base_names) == 0:
            base_names = ["Contract"]

        self.generate_contract_template(contract, ", ".join(base_names))

        if contract.enums:
            self.generate_types_enum(contract.enums, 1)

        if contract.structs:
            self.generate_types_struct(contract.structs, 1)

        if contract.errors:
            self.generate_types_error(contract.errors, 1)

        if contract.events:
            self.generate_types_event(contract.events, 1)

        selector_assignments = []

        for var in contract.declared_variables:
            if (
                var.visibility == Visibility.EXTERNAL
                or var.visibility == Visibility.PUBLIC
            ):
                self.generate_getter_for_state_var(var)
                selector_assignments.append((self.get_name(var), var.function_selector))
        for fn in contract.functions:
            if fn.function_selector:
                if contract.kind != ContractKind.LIBRARY or fn.state_mutability in {
                    StateMutability.VIEW,
                    StateMutability.PURE,
                }:
                    self.generate_types_function(fn)
                    selector_assignments.append(
                        (self.get_name(fn), fn.function_selector)
                    )

        for fn_name, selector in selector_assignments:
            self.add_str_to_types(
                0, f"{self.get_name(contract)}.{fn_name}.selector = {selector}", 1
            )

    def generate_types_source_unit(self, unit: SourceUnit) -> None:
        self.generate_types_struct(unit.structs, 0)
        self.generate_types_enum(unit.enums, 0)
        self.generate_types_error(unit.errors, 0)
        self.generate_types_event(unit.events, 0)

        for contract in unit.contracts:
            self.generate_types_contract(contract)
            for user_defined_value_type in contract.user_defined_value_types:
                self.__user_defined_value_types_index[
                    f"t_userDefinedValueType({user_defined_value_type.name}){user_defined_value_type.ast_node_id}"
                ] = user_defined_value_type.underlying_type.type_identifier
        for user_defined_value_type in unit.user_defined_value_types:
            self.__user_defined_value_types_index[
                f"t_userDefinedValueType({user_defined_value_type.name}){user_defined_value_type.ast_node_id}"
            ] = user_defined_value_type.underlying_type.type_identifier

    def clean_type_dir(self):
        """
        instead of recursive removal of type files inside pytypes dir
        remove the root and recreate it
        """
        if self.__pytypes_dir.exists():
            shutil.rmtree(self.__pytypes_dir)
        self.__pytypes_dir.mkdir(exist_ok=True)

    def write_source_unit_to_file(self, contract_name: str):
        lists = ""
        for a in self.__fixed_size_arrays:
            lists += f"class List{a}(FixedSizeList[T]):\n    length = {a}\n\n\n"

        self.__pytypes_dir.mkdir(exist_ok=True)
        contract_name = _make_path_alphanum(contract_name[:-3])
        unit_path = (self.__pytypes_dir / contract_name).with_suffix(".py")
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(str(self.__imports) + lists + self.__source_unit_types)

    # clean the instance variables to enable generating a new source unit
    def cleanup_source_unit(self):
        self.__source_unit_types = ""
        self.__imports.cleanup_imports()
        self.__fixed_size_arrays.clear()

    def add_func_overload_if_match(
        self, fn: FunctionDefinition, contract: ContractDefinition
    ):
        for function in contract.functions:
            # this function is called also with the contract in which the function is defined
            # thus we need to ensure that we don't compare the function with itself
            if (
                fn.name == function.name and fn != function
            ):  # and len(fn.parameters.parameters) == len(function.parameters.parameters):
                # both functions have to be overloded -> add both
                if isinstance(fn.parent, ContractDefinition):
                    source_unit = fn.parent.parent
                else:
                    source_unit = fn.parent
                # there can be 2 contracts with the same name and both of them can define function with the same name
                # thus to uniquely idenify the funtion also the source unit has to be used, otherwise it could happen
                # that an incorrect function gets overloaded
                self.__func_to_overload.add(
                    source_unit.source_unit_name + fn.canonical_name
                )
                self.__func_to_overload.add(
                    contract.parent.source_unit_name + function.canonical_name
                )
                # print("-------------------")
                # print(f"overload: {fn.canonical_name} {fn.parent.canonical_name}")
                # print(f"overload: {function.canonical_name} {contract.canonical_name}")
                # print("-------------------")

    # TODO add check if func not in __func_to_overload for optimization
    def traverse_funcs_in_child_contracts(
        self, fn: FunctionDefinition, contract: ContractDefinition
    ):
        for child in contract.child_contracts:
            self.add_func_overload_if_match(fn, child)

        for child in contract.child_contracts:
            self.traverse_funcs_in_child_contracts(fn, child)

    # TODO add check if func not in __func_to_overload
    def traverse_funcs_in_parent_contracts(
        self, fn: FunctionDefinition, contract: ContractDefinition
    ):
        for inh_spec in contract.base_contracts:
            if not contract.kind == ContractKind.INTERFACE:
                parent_contract = inh_spec.base_name.referenced_declaration
                assert isinstance(parent_contract, ContractDefinition)
                self.add_func_overload_if_match(fn, parent_contract)
        for inh_spec in contract.base_contracts:
            if not contract.kind == ContractKind.INTERFACE:
                parent_contract = inh_spec.base_name.referenced_declaration
                assert isinstance(parent_contract, ContractDefinition)
                self.traverse_funcs_in_parent_contracts(fn, parent_contract)

    # TODO travesrse also state variables as getters are generated for them and thus overlaoding might be necessary
    def traverse_funcs_to_check_overload(self):
        # set containing canonical names of functions to be overloaded
        for _, unit in self.__source_units.items():
            for contract in unit.contracts:
                # interface function can't have implementation and thus can't be overloaded
                if contract.kind != ContractKind.INTERFACE:
                    for fn in contract.functions:
                        if (
                            not fn.canonical_name in self.__func_to_overload
                            and fn.implemented
                            and fn.function_selector
                        ):
                            # we create pytypes only for functions that are publicly accessible
                            if (
                                fn.visibility == Visibility.PUBLIC
                                or fn.visibility == Visibility.EXTERNAL
                            ):
                                self.add_func_overload_if_match(fn, contract)
                                self.traverse_funcs_in_parent_contracts(fn, contract)
                                self.traverse_funcs_in_child_contracts(fn, contract)
            # if unit.source_unit_name == "overloading.sol":
            #    print(self.__func_to_overload)

    def generate_types(self, compiler: SolidityCompiler) -> None:
        def generate_source_unit(source_unit: SourceUnit) -> None:
            self.__current_source_unit = source_unit.source_unit_name
            self.generate_types_source_unit(source_unit)
            self.write_source_unit_to_file(source_unit.source_unit_name)
            self.cleanup_source_unit()
            self.__name_sanitizer.clear_global_renames()

        build = compiler.latest_build
        assert build is not None
        self.__interval_trees = build.interval_trees
        self.__source_units = build.source_units
        self.__reference_resolver = build.reference_resolver

        self.clean_type_dir()

        # generate source units in import order, source units with no imports are generated first
        # also handle cyclic imports
        assert compiler.latest_graph is not None
        assert compiler.latest_source_units_to_paths
        graph: nx.DiGraph = (
            compiler.latest_graph.copy()
        )  # pyright: ignore reportGeneralTypeIssues
        source_units_to_paths = compiler.latest_source_units_to_paths
        paths_to_source_unit_names: DefaultDict[Path, Set[str]] = defaultdict(set)
        for source_unit, path in source_units_to_paths.items():
            paths_to_source_unit_names[path].add(source_unit)

        previous_len = len(graph)
        cycles_detected = False
        cycles: Set[FrozenSet[str]] = set()
        generated_paths: Set[Path] = set()

        # keep generating pytypes for source units that have all import dependencies already generated
        # take into account cyclic imports - generate pytypes for a cycle if all not yet generated import dependencies are in the cycle
        while len(graph) > 0:
            # use heapq to make order of source units deterministic
            sources: List[str] = [
                node
                for node, in_degree in graph.in_degree()  # pyright: ignore reportGeneralTypeIssues
                if in_degree == 0
            ]
            heapq.heapify(sources)
            visited: Set[str] = set(sources)

            while len(sources) > 0:
                source = heapq.heappop(sources)
                path = source_units_to_paths[source]
                if path in self.__source_units and path not in generated_paths:
                    generate_source_unit(self.__source_units[path])
                    generated_paths.add(path)

                for source_unit_name in paths_to_source_unit_names[path]:
                    visited.add(source_unit_name)
                    for (
                        _,
                        to,
                    ) in graph.out_edges(  # pyright: ignore reportGeneralTypeIssues
                        source_unit_name  # pyright: ignore reportGeneralTypeIssues
                    ):
                        if (
                            graph.in_degree(
                                to  # pyright: ignore reportGeneralTypeIssues
                            )
                            == 1
                        ):
                            heapq.heappush(sources, to)
                            visited.add(to)
                graph.remove_nodes_from(paths_to_source_unit_names[path])

            generated_cycles: Set[FrozenSet[str]] = set()
            simple_cycles = [set(c) for c in nx.simple_cycles(graph)]
            if len(simple_cycles) > 0:
                # used for reporting to user
                cycles_detected = True
                cycles.update([frozenset(c) for c in simple_cycles])

            for simple_cycle in simple_cycles:
                if any(simple_cycle.issubset(c) for c in generated_cycles):
                    # source units in this cycle were already marked to be generated
                    continue

                # merge with as many other cycles as possible (create transitive closure)
                for other_cycle in simple_cycles:
                    if len(simple_cycle & other_cycle) > 0:
                        simple_cycle |= other_cycle

                is_closed_cycle = True
                for node in simple_cycle:
                    if any(
                        edge[0] not in simple_cycle
                        for edge in graph.in_edges(
                            node  # pyright: ignore reportGeneralTypeIssues
                        )
                    ):
                        is_closed_cycle = False
                        break

                if is_closed_cycle:
                    generated_cycles.add(frozenset(simple_cycle))

                    # update cyclic source units index used when generating pytypes
                    for source_unit_name in simple_cycle:
                        self.__cyclic_source_units[source_unit_name].update(
                            s for s in simple_cycle if s != source_unit_name
                        )

            for cycle in sorted(generated_cycles):
                for source in cycle:
                    path = source_units_to_paths[source]
                    if path in self.__source_units and path not in generated_paths:
                        generate_source_unit(self.__source_units[path])
                        generated_paths.add(path)
                    graph.remove_nodes_from(paths_to_source_unit_names[path])

            if len(graph) == previous_len:
                # avoid infinite loop
                # in a happy world, this should never happen
                break
            previous_len = len(graph)

        if cycles_detected:
            logger.info(
                "Cyclic imports detected\n"
                + "\n".join(str(set(cycle)) for cycle in cycles)
            )

        if len(graph.nodes) > 0:  # pyright: ignore reportGeneralTypeIssues
            logger.warning(
                "Failed to generate pytypes for the following source units:\n"
                + "\n".join(graph.nodes)  # pyright: ignore reportGeneralTypeIssues
            )

        init_path = self.__pytypes_dir / "__init__.py"
        init_path.write_text(
            INIT_CONTENT.format(
                version=get_package_version("eth-wake"),
                errors=self.__errors_index,
                events=self.__events_index,
                contracts_by_fqn=self.__contracts_index,
                contracts_by_metadata=self.__contracts_by_metadata_index,
                contracts_inheritance=self.__contracts_inheritance_index,
                contracts_revert_constructor_index=self.__contracts_revert_constructor_index,
                contracts_revert_index=self.__contracts_revert_index,
                creation_code_index=self.__creation_code_index,
                user_defined_value_types_index=self.__user_defined_value_types_index,
            )
        )


class SourceUnitImports:
    __all_imports: str
    __struct_imports: Set[str]
    __enum_imports: Set[str]
    __contract_imports: Set[str]
    __python_imports: Set[str]
    __type_checking_imports: Set[str]
    __lazy_modules: Set[str]
    __type_gen: TypeGenerator

    def __init__(self, outer: TypeGenerator):
        self.__struct_imports = set()
        self.__enum_imports = set()
        self.__all_imports = ""
        self.__contract_imports = set()
        self.__python_imports = set()
        self.__type_checking_imports = set()
        self.__lazy_modules = set()
        self.__type_gen = outer

    def __str__(self) -> str:
        self.__add_str_to_imports(0, DEFAULT_IMPORTS, 1)

        for python_import in sorted(self.__python_imports):
            self.__add_str_to_imports(0, python_import, 1)

        if self.__python_imports:
            self.__add_str_to_imports(0, "", 1)

        for contract in sorted(self.__contract_imports):
            self.__add_str_to_imports(0, contract, 1)

        if self.__contract_imports:
            self.__add_str_to_imports(0, "", 1)

        for struct in sorted(self.__struct_imports):
            self.__add_str_to_imports(0, struct, 1)

        if self.__struct_imports:
            self.__add_str_to_imports(0, "", 1)

        for enum in sorted(self.__enum_imports):
            self.__add_str_to_imports(0, enum, 1)

        if self.__enum_imports:
            self.__add_str_to_imports(0, "", 1)

        if self.__type_checking_imports:
            self.__add_str_to_imports(0, "from typing import TYPE_CHECKING", 1)
            self.__add_str_to_imports(0, "if TYPE_CHECKING:", 1)
            for type_checking_import in sorted(self.__type_checking_imports):
                self.__add_str_to_imports(1, type_checking_import, 1)

            if self.__lazy_modules:
                self.__add_str_to_imports(0, "else:", 1)
                self.__add_str_to_imports(1, "import lazy_import", 2)

                for lazy_module in sorted(self.__lazy_modules):
                    self.__add_str_to_imports(1, lazy_module, 1)
            self.__add_str_to_imports(0, "", 1)

        self.__add_str_to_imports(0, "", 2)

        return self.__all_imports

    def cleanup_imports(self) -> None:
        self.__struct_imports.clear()
        self.__enum_imports.clear()
        self.__contract_imports.clear()
        self.__python_imports.clear()
        self.__type_checking_imports.clear()
        self.__lazy_modules.clear()
        self.__all_imports = ""

    def __generate_import(
        self,
        declaration: DeclarationAbc,
        source_unit_name: str,
        *,
        aliased: bool = False,
    ) -> str:
        source_unit_name = _make_path_alphanum(source_unit_name)
        name = self.__type_gen.get_name(declaration, force_simple=True)

        if aliased:
            return f"import pytypes.{source_unit_name[:-3].replace('/', '.')} as {name}"
        return f"from pytypes.{source_unit_name[:-3].replace('/', '.')} import {name}"

    def __generate_lazy_module(
        self, declaration: DeclarationAbc, source_unit_name: str
    ) -> str:
        source_unit_name = _make_path_alphanum(source_unit_name)
        name = self.__type_gen.get_name(declaration, force_simple=True)

        return f"{name} = lazy_import.lazy_module('pytypes.{source_unit_name[:-3].replace('/', '.')}')"

    def __add_str_to_imports(
        self, num_of_indentation: int, string: str, num_of_newlines: int
    ):
        self.__all_imports += (
            num_of_indentation * TAB_WIDTH * " " + string + num_of_newlines * "\n"
        )

    def generate_struct_import(self, struct_type: types.Struct):
        node = struct_type.ir_node
        if isinstance(node.parent, ContractDefinition):
            source_unit = node.parent.parent
        else:
            source_unit = node.parent
        # only those structs that are defined in a different source unit should be imported
        if source_unit.source_unit_name == self.__type_gen.current_source_unit:
            return

        if source_unit.source_unit_name in self.__type_gen.cyclic_source_units:
            struct_import = self.__generate_import(
                struct_type.ir_node, source_unit.source_unit_name, aliased=True
            )
            self.__type_checking_imports.add(struct_import)
            self.__lazy_modules.add(
                self.__generate_lazy_module(
                    struct_type.ir_node, source_unit.source_unit_name
                )
            )
        else:
            struct_import = self.__generate_import(
                struct_type.ir_node, source_unit.source_unit_name
            )
            self.__struct_imports.add(struct_import)

    # only used for top-level enums (not within contracts)
    def generate_enum_import(self, enum_type: types.Enum):
        source_unit = enum_type.ir_node.parent
        assert isinstance(source_unit, SourceUnit)

        # only those structs that are defined in a different source unit should be imported
        if source_unit.source_unit_name == self.__type_gen.current_source_unit:
            return

        if source_unit.source_unit_name in self.__type_gen.cyclic_source_units:
            enum_import = self.__generate_import(
                enum_type.ir_node, source_unit.source_unit_name, aliased=True
            )
            self.__type_checking_imports.add(enum_import)
            self.__lazy_modules.add(
                self.__generate_lazy_module(
                    enum_type.ir_node, source_unit.source_unit_name
                )
            )
        else:
            enum_import = self.__generate_import(
                enum_type.ir_node, source_unit.source_unit_name
            )
            self.__enum_imports.add(enum_import)

    def generate_contract_import(
        self, contract: ContractDefinition, *, force: bool = False
    ):
        source_unit = contract.parent
        if source_unit.source_unit_name == self.__type_gen.current_source_unit:
            return

        contract_import = self.__generate_import(contract, source_unit.source_unit_name)

        if (
            not force
            and contract_import not in self.__contract_imports
            and source_unit.source_unit_name in self.__type_gen.cyclic_source_units
        ):
            contract_import = self.__generate_import(
                contract, source_unit.source_unit_name, aliased=True
            )

            self.__type_checking_imports.add(contract_import)
            self.__lazy_modules.add(
                self.__generate_lazy_module(contract, source_unit.source_unit_name)
            )
        else:
            self.__contract_imports.add(contract_import)

    def add_python_import(self, p_import: str) -> None:
        self.__python_imports.add(p_import)


class NameSanitizer:
    __global_reserved: Set[str]
    __contract_reserved: Set[str]
    __function_reserved: Set[str]
    __struct_reserved: Set[str]
    __event_reserved: Set[str]
    __error_reserved: Set[str]
    __enum_reserved: Set[str]

    __global_renames: Dict[DeclarationAbc, str]
    __contract_renames: DefaultDict[ContractDefinition, Dict[DeclarationAbc, str]]
    __function_renames: DefaultDict[FunctionDefinition, Dict[DeclarationAbc, str]]
    __struct_renames: DefaultDict[StructDefinition, Dict[DeclarationAbc, str]]
    __event_renames: DefaultDict[EventDefinition, Dict[DeclarationAbc, str]]
    __error_renames: DefaultDict[ErrorDefinition, Dict[DeclarationAbc, str]]
    __enum_renames: DefaultDict[EnumDefinition, Dict[DeclarationAbc, str]]

    def __init__(self):
        self.__global_reserved = {
            "Dict",
            "List",
            "Mapping",
            "Set",
            "Tuple",
            "Union",
            "Annotated",
            "Optional",
            "Literal",
            "Callable",
            "Path",
            "bytearray",
            "IntEnum",
            "dataclasses",
            "overload",
            "Contract",
            "Library",
            "Address",
            "Account",
            "Chain",
            "RequestType",
            "TransactionRevertedError",
            "TransactionAbc",
            "LegacyTransaction",
            "Eip2930Transaction",
            "Eip1559Transaction",
            "ValueRange",
            "Length",
            "bytes",
            "int",
            "uint",
            "str",
            "bool",
            "FixedSizeList",
            "T",
            "FixedSizeBytes",
            "Integer",
        }

        for i in range(8, 257, 8):
            self.__global_reserved.add(f"uint{i}")
            self.__global_reserved.add(f"int{i}")

        for i in range(1, 33):
            self.__global_reserved.add(f"bytes{i}")
            self.__global_reserved.add(f"List{i}")

        self.__contract_reserved = {
            "_abi",
            "_creation_code",
            "_address",
            "_chain",
            "_label",
            "_get_creation_code",
            "_deploy",
            "_execute",
            "_library_id",
            "_prepare_tx_params",
            "_storage_layout",
            "address",
            "label",
            "balance",
            "code",
            "chain",
            "nonce",
            "call",
            "transact",
            "estimate",
            "deploy",
            "get_creation_code",
        }
        self.__function_reserved = {
            "self",
            "cls",
            "from_",
            "value",
            "gas_limit",
            "return_tx",
            "chain",
            "to",
            "request_type",
            "gas_price",
            "max_fee_per_gas",
            "max_priority_fee_per_gas",
            "access_list",
            "block",
            "confirmations",
        }
        self.__struct_reserved = {"original_name"}
        self.__event_reserved = {"_abi", "selector", "original_name", "origin"}
        self.__error_reserved = {"_abi", "selector", "original_name"}
        self.__enum_reserved = set()

        self.__global_renames = {}
        self.__contract_renames = defaultdict(dict)
        self.__function_renames = defaultdict(dict)
        self.__struct_renames = defaultdict(dict)
        self.__event_renames = defaultdict(dict)
        self.__error_renames = defaultdict(dict)
        self.__enum_renames = defaultdict(dict)

    def _check_global(self, name: str) -> bool:
        return (
            name in self.__global_reserved
            or name in set(self.__global_renames.values())
            or keyword.iskeyword(name)
        )

    def _check_contract(self, name: str, contract: ContractDefinition) -> bool:
        return (
            name in self.__global_reserved
            or name in set(self.__global_renames)
            or name in self.__contract_reserved
            or name in set(self.__contract_renames[contract].values())
            or keyword.iskeyword(name)
            or (
                name.startswith("__")
                and name.endswith("__")
                and not name.endswith("___")
            )
        )

    def _check_function(self, name: str, function: FunctionDefinition) -> bool:
        return (
            name in self.__global_reserved
            or name in set(self.__global_renames)
            or name in self.__function_reserved
            or name in set(self.__function_renames[function].values())
            or keyword.iskeyword(name)
        )

    def _check_struct(self, name: str, struct: StructDefinition) -> bool:
        return (
            name in self.__global_reserved
            or name in set(self.__global_renames)
            or name in self.__struct_reserved
            or name in set(self.__struct_renames[struct].values())
            or keyword.iskeyword(name)
            or (
                name.startswith("__")
                and name.endswith("__")
                and not name.endswith("___")
            )
        )

    def _check_event(self, name: str, event: EventDefinition) -> bool:
        return (
            name in self.__global_reserved
            or name in set(self.__global_renames)
            or name in self.__event_reserved
            or name in set(self.__event_renames[event].values())
            or keyword.iskeyword(name)
            or (
                name.startswith("__")
                and name.endswith("__")
                and not name.endswith("___")
            )
        )

    def _check_error(self, name: str, error: ErrorDefinition) -> bool:
        return (
            name in self.__global_reserved
            or name in set(self.__global_renames)
            or name in self.__error_reserved
            or name in set(self.__error_renames[error].values())
            or keyword.iskeyword(name)
            or (
                name.startswith("__")
                and name.endswith("__")
                and not name.endswith("___")
            )
        )

    def _check_enum(self, name: str, enum: EnumDefinition) -> bool:
        return (
            name in self.__global_reserved
            or name in set(self.__global_renames)
            or name in self.__enum_reserved
            or name in set(self.__enum_renames[enum].values())
            or keyword.iskeyword(name)
            or (
                name.startswith("__")
                and name.endswith("__")
                and not name.endswith("___")
            )
        )

    def clear_global_renames(self):
        self.__global_renames = {}

    def sanitize_name(self, declaration: DeclarationAbc) -> str:
        parent = declaration.parent
        if isinstance(parent, SourceUnit):
            check = self._check_global
            renames = self.__global_renames
        elif isinstance(parent, ContractDefinition):
            check = lambda name: self._check_contract(name, parent)
            renames = self.__contract_renames[parent]
        elif isinstance(parent, StructDefinition):
            check = lambda name: self._check_struct(name, parent)
            renames = self.__struct_renames[parent]
        elif isinstance(parent, EnumDefinition):
            check = lambda name: self._check_enum(name, parent)
            renames = self.__enum_renames[parent]
        elif isinstance(parent, ParameterList):
            parent_parent = parent.parent
            if isinstance(parent_parent, FunctionDefinition):
                check = lambda name: self._check_function(name, parent_parent)
                renames = self.__function_renames[parent_parent]
            elif isinstance(parent_parent, EventDefinition):
                check = lambda name: self._check_event(name, parent_parent)
                renames = self.__event_renames[parent_parent]
            elif isinstance(parent_parent, ErrorDefinition):
                check = lambda name: self._check_error(name, parent_parent)
                renames = self.__error_renames[parent_parent]
            else:
                raise NotImplementedError(
                    f"Cannot sanitize name for declaration {declaration} with parent {parent} and parent of parent {parent_parent}"
                )
        else:
            raise NotImplementedError(
                f"Cannot sanitize name for declaration {declaration} with parent {parent}"
            )

        if declaration in renames:
            return renames[declaration]

        new_name = declaration.name.replace("$", "_")
        while new_name.startswith("__"):
            new_name = new_name[1:]

        while check(new_name):
            new_name = new_name + "_"

        renames[declaration] = new_name
        return new_name
