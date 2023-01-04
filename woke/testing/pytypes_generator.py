from __future__ import annotations

import asyncio
import keyword
import re
import shutil
import string
from collections import deque
from enum import Enum
from operator import itemgetter
from pathlib import Path, PurePath
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

import eth_utils
from Crypto.Hash import BLAKE2b, keccak
from intervaltree import IntervalTree
from rich.panel import Panel
from typing_extensions import Literal

import woke.ast.ir.type_name.mapping
import woke.ast.types as types
from woke.ast.enums import *
from woke.ast.ir.declaration.enum_definition import EnumDefinition
from woke.ast.ir.declaration.struct_definition import StructDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.nodes import AstSolc
from woke.compile import SolcOutput, SolidityCompiler
from woke.compile.solc_frontend.input_data_model import SolcOutputSelectionEnum
from woke.config import WokeConfig

from ..ast.ir.declaration.contract_definition import ContractDefinition
from ..ast.ir.declaration.error_definition import ErrorDefinition
from ..ast.ir.declaration.event_definition import EventDefinition
from ..ast.ir.declaration.function_definition import FunctionDefinition
from ..ast.ir.expression.function_call import FunctionCall
from ..ast.ir.meta.source_unit import SourceUnit
from ..ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from ..ast.ir.statement.revert_statement import RevertStatement
from ..ast.ir.type_name.abc import TypeNameAbc
from ..ast.ir.type_name.array_type_name import ArrayTypeName
from ..ast.ir.type_name.user_defined_type_name import UserDefinedTypeName
from ..ast.ir.utils import IrInitTuple
from ..cli.console import console
from ..compile.compilation_unit import CompilationUnit
from ..compile.solc_frontend import SolcOutputErrorSeverityEnum
from ..utils.file_utils import is_relative_to
from .constants import DEFAULT_IMPORTS, INIT_CONTENT, TAB_WIDTH


class RequestType(str, Enum):
    CALL = "call"
    DEBUG = "debug"
    TRACE = "trace"
    DEFAULT = "default"  # default request type for the given network


# TODO ensure that making the path alphanum won't create collisions
def _make_path_alphanum(source_unit_name: str) -> str:
    filtered = "".join(
        filter(lambda ch: ch.isalnum() or ch == "/" or ch == "_", source_unit_name)
    )
    return "/".join(
        f"_{segment}" if segment.startswith(tuple(string.digits)) else segment
        for segment in filtered.split("/")
    )


def _parse_opcodes(opcodes: str) -> List[Tuple[int, str, int, Optional[int]]]:
    pc_op_map = []
    opcodes_spl = opcodes.split(" ")

    pc = 0
    ignore = False

    for i, opcode in enumerate(opcodes_spl):
        if ignore:
            ignore = False
            continue

        if not opcode.startswith("PUSH"):
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
) -> Dict[int, Tuple[int, int, int]]:
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

        pc_map[pc] = (last_data[0], last_data[0] + last_data[1], last_data[2])

    return pc_map


class TypeGenerator:
    LIBRARY_PLACEHOLDER_REGEX = re.compile(r"__\$[0-9a-fA-F]{34}\$__")

    __config: WokeConfig
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
    __errors_index: Dict[bytes, Dict[str, Any]]
    __events_index: Dict[bytes, Dict[str, Any]]
    __contracts_by_metadata_index: Dict[bytes, str]
    __contracts_inheritance_index: Dict[str, Tuple[str, ...]]
    __contracts_revert_index: Dict[str, Set[int]]
    __deployment_code_index: List[Tuple[Tuple[Tuple[int, bytes], ...], str]]

    def __init__(self, config: WokeConfig, return_tx_obj: bool):
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
        self.__errors_index = {}
        self.__events_index = {}
        self.__contracts_by_metadata_index = {}
        self.__contracts_inheritance_index = {}
        self.__contracts_revert_index = {}
        self.__deployment_code_index = []

        # built-in Error(str) and Panic(uint256) errors
        error_abi = {
            "name": "Error",
            "type": "error",
            "inputs": [{"name": "message", "type": "string"}],
        }
        panic_abi = {
            "name": "Panic",
            "type": "error",
            "inputs": [{"name": "code", "type": "uint256"}],
        }

        for item in [error_abi, panic_abi]:
            selector = eth_utils.function_abi_to_4byte_selector(
                item
            )  # pyright: reportPrivateImportUsage=false
            self.__errors_index[selector] = {}
            self.__errors_index[selector][""] = (
                "woke.testing.internal",
                (item["name"],),
            )

    # TODO do some prettier init :)
    def __init_sol_to_py_types(self):
        self.__sol_to_py_lookup[types.UInt.__name__] = ("int", "int")
        self.__sol_to_py_lookup[types.Int.__name__] = ("int", "int")
        self.__sol_to_py_lookup[types.Address.__name__] = (
            "Union[Account, Address]",
            "Address",
        )
        self.__sol_to_py_lookup[types.String.__name__] = ("str", "str")
        self.__sol_to_py_lookup[types.Bool.__name__] = ("bool", "bool")
        self.__sol_to_py_lookup[types.FixedBytes.__name__] = (
            "Union[bytearray, bytes]",
            "bytearray",
        )
        self.__sol_to_py_lookup[types.Bytes.__name__] = (
            "Union[bytearray, bytes]",
            "bytearray",
        )
        self.__sol_to_py_lookup[types.Function.__name__] = ("Callable", "TODO")

    @property
    def current_source_unit(self):
        return self.__current_source_unit

    def run_compile(self, warnings: bool) -> None:
        """Compile the project."""
        sol_files: Set[Path] = set()
        for file in self.__config.project_root_path.rglob("**/*.sol"):
            if (
                not any(
                    is_relative_to(file, p)
                    for p in self.__config.compiler.solc.ignore_paths
                )
                and file.is_file()
            ):
                sol_files.add(file)

        compiler = SolidityCompiler(self.__config)
        outputs: List[Tuple[CompilationUnit, SolcOutput]] = asyncio.run(
            compiler.compile(
                sol_files,
                [SolcOutputSelectionEnum.ALL],
                write_artifacts=(True),
                reuse_latest_artifacts=(True),
                maximize_compilation_units=True,
            )
        )

        errored = False
        for _, output in outputs:
            for error in output.errors:
                if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                    errored = True
                if warnings or error.severity == SolcOutputErrorSeverityEnum.ERROR:
                    if error.formatted_message is not None:
                        console.print(Panel(error.formatted_message, highlight=True))
                    else:
                        console.print(Panel(error.message, highlight=True))

        if errored:
            raise Exception("Compilation failed")

        processed_files: Set[Path] = set()

        for cu, output in outputs:
            for source_unit_name, info in output.sources.items():
                path = cu.source_unit_name_to_path(PurePath(source_unit_name))

                ast = AstSolc.parse_obj(info.ast)

                self.__reference_resolver.register_source_file_id(
                    info.id, path, cu.hash
                )
                self.__reference_resolver.index_nodes(ast, path, cu.hash)

                if path in processed_files:
                    continue
                processed_files.add(path)
                self.__interval_trees[path] = IntervalTree()

                init = IrInitTuple(
                    path,
                    path.read_bytes(),
                    cu,
                    self.__interval_trees[path],
                    self.__reference_resolver,
                    output.contracts[source_unit_name]
                    if source_unit_name in output.contracts
                    else None,
                )
                self.__source_units[path] = SourceUnit(init, ast)

        self.__reference_resolver.run_post_process_callbacks(
            CallbackParams(
                interval_trees=self.__interval_trees, source_units=self.__source_units
            )
        )

    def add_str_to_types(
        self, num_of_indentation: int, string: str, num_of_newlines: int
    ):
        self.__source_unit_types += (
            num_of_indentation * TAB_WIDTH * " " + string + num_of_newlines * "\n"
        )

    def get_name(self, name: str) -> str:
        return self.__name_sanitizer.sanitize_name(name)

    def generate_deploy_func(
        self, contract: ContractDefinition, libraries: Dict[bytes, Tuple[str, str]]
    ):
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

        contract_name = self.get_name(contract.name)

        # generate @overload stubs
        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f'def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: int = 0, gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max", return_tx: Literal[False] = False{libraries_str}, chain: Optional[ChainInterface] = None) -> {contract_name}:',
            1,
        )
        self.add_str_to_types(2, "...", 2)

        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f'def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: int = 0, gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max", return_tx: Literal[True] = True{libraries_str}, chain: Optional[ChainInterface] = None) -> LegacyTransaction[{contract_name}]:',
            1,
        )
        self.add_str_to_types(2, "...", 2)

        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f'def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: int = 0, gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max", return_tx: bool = {self.__return_tx_obj}{libraries_str}, chain: Optional[ChainInterface] = None) -> Union[{contract_name}, LegacyTransaction[{contract_name}]]:',
            1,
        )

        if len(param_names) > 0:
            self.add_str_to_types(2, '"""', 1)
            self.add_str_to_types(2, "Args:", 1)
            for param_name, param_type in param_names:
                self.add_str_to_types(3, f"{param_name}: {param_type}", 1)
            self.add_str_to_types(2, '"""', 1)

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
                    f"return cls._deploy([{', '.join(map(itemgetter(0), param_names))}], return_tx, {contract_name}, from_, value, gas_limit, {libs_arg}, chain)",
                    1,
                )
            else:
                self.add_str_to_types(
                    2, 'raise Exception("Cannot deploy abstract contract")', 1
                )
        else:
            self.add_str_to_types(2, 'raise Exception("Cannot deploy interface")', 1)

    def generate_deployment_code_func(
        self, contract: ContractDefinition, libraries: Dict[bytes, Tuple[str, str]]
    ):
        libraries_arg = "".join(
            f", {l[0]}: Union[{l[1]}, Address]" for l in libraries.values()
        )

        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(
            1,
            f"def deployment_code(cls{libraries_arg}) -> bytes:",
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
                    f"return cls._get_deployment_code({libs_arg})",
                    1,
                )
            else:
                self.add_str_to_types(
                    2,
                    'raise Exception("Cannot get deployment code of an abstract contract")',
                    1,
                )
        else:
            self.add_str_to_types(
                2, 'raise Exception("Cannot get deployment code of an interface")', 1
            )

    def generate_contract_template(
        self, contract: ContractDefinition, base_names: str
    ) -> Dict[bytes, Any]:
        if contract.kind == ContractKind.LIBRARY:
            self.add_str_to_types(
                0, "class " + self.get_name(contract.name) + "(Library):", 1
            )
        else:
            self.add_str_to_types(
                0, "class " + self.get_name(contract.name) + "(" + base_names + "):", 1
            )
        compilation_info = contract.compilation_info
        assert compilation_info is not None
        assert compilation_info.abi is not None
        assert compilation_info.evm is not None
        assert compilation_info.evm.bytecode is not None
        assert compilation_info.evm.bytecode.object is not None
        assert compilation_info.evm.deployed_bytecode is not None
        assert compilation_info.evm.deployed_bytecode.object is not None
        assert compilation_info.evm.deployed_bytecode.opcodes is not None
        assert compilation_info.evm.deployed_bytecode.source_map is not None

        fqn = f"{contract.parent.source_unit_name}:{contract.name}"
        parsed_opcodes = _parse_opcodes(compilation_info.evm.deployed_bytecode.opcodes)
        pc_map = _parse_source_map(
            compilation_info.evm.deployed_bytecode.source_map, parsed_opcodes
        )

        for pc, op, size, argument in parsed_opcodes:
            if op == "REVERT" and pc in pc_map:
                start, end, file_id = pc_map[pc]
                if file_id == -1:
                    continue
                try:
                    path = self.__reference_resolver.resolve_source_file_id(
                        file_id, contract.cu_hash
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

                        if fqn not in self.__contracts_revert_index:
                            self.__contracts_revert_index[fqn] = set()
                        self.__contracts_revert_index[fqn].add(pc)

        if len(compilation_info.evm.deployed_bytecode.object) > 0:
            metadata = bytes.fromhex(
                compilation_info.evm.deployed_bytecode.object[-106:]
            )
            assert len(metadata) == 53
            assert metadata not in self.__contracts_by_metadata_index
            self.__contracts_by_metadata_index[metadata] = fqn

        assert fqn not in self.__contracts_inheritance_index
        self.__contracts_inheritance_index[fqn] = tuple(
            f"{base.parent.source_unit_name}:{base.name}"
            for base in contract.linearized_base_contracts
        )

        abi_by_selector: Dict[Union[bytes, Literal["constructor"]], Dict] = {}

        module_name = "pytypes." + _make_path_alphanum(
            contract.parent.source_unit_name[:-3]
        ).replace("/", ".")

        events_abi = {}

        for item in compilation_info.abi:
            if item["type"] == "function":
                selector = eth_utils.function_abi_to_4byte_selector(
                    item
                )  # pyright: reportPrivateImportUsage=false
                abi_by_selector[selector] = item
            elif item["type"] == "error":
                selector = eth_utils.function_abi_to_4byte_selector(
                    item
                )  # pyright: reportPrivateImportUsage=false

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
                        (error_decl.parent.name, error_decl.name),
                    )
                elif isinstance(error_decl.parent, SourceUnit):
                    error_module_name = "pytypes." + _make_path_alphanum(
                        error_decl.parent.source_unit_name[:-3]
                    ).replace("/", ".")
                    self.__errors_index[selector][fqn] = (
                        error_module_name,
                        (error_decl.name,),
                    )
                else:
                    raise Exception("Unknown error parent")
            elif item["type"] == "event":
                selector = eth_utils.event_abi_to_log_topic(
                    item
                )  # pyright: reportPrivateImportUsage=false
                events_abi[selector] = item

                if selector not in self.__events_index:
                    self.__events_index[selector] = {}
                self.__events_index[selector][fqn] = (
                    module_name,
                    (contract.name, item["name"]),
                )
            elif item["type"] == "constructor":
                abi_by_selector["constructor"] = item
            elif item["type"] in {"fallback", "receive"}:
                continue
            else:
                raise Exception(f"Unexpected ABI item type: {item['type']}")
        self.add_str_to_types(1, f"_abi = {abi_by_selector}", 1)
        self.add_str_to_types(
            1, f'_deployment_code = "{compilation_info.evm.bytecode.object}"', 2
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

            self.__deployment_code_index.append((tuple(bytecode_segments), fqn))

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
                        self.__imports.generate_contract_import_name(
                            c.name, c.parent.source_unit_name
                        )
                        libraries[lib_id] = (
                            c.name[0].lower() + c.name[1:],
                            self.get_name(c.name),
                        )

            source_units_queue.extend(imp.source_unit for imp in source_unit.imports)

        assert len(lib_ids) == 0, "Not all libraries were found"

        self.__imports.add_python_import("from __future__ import annotations")
        self.generate_deploy_func(contract, libraries)
        self.add_str_to_types(0, "", 1)
        self.generate_deployment_code_func(contract, libraries)
        self.add_str_to_types(0, "", 1)

        return events_abi

    def generate_types_struct(
        self, structs: Iterable[StructDefinition], indent: int
    ) -> None:
        for struct in structs:
            members: List[Tuple[str, str, str]] = []
            for member in struct.members:
                member_name = self.get_name(member.name)
                member_type = self.parse_type_and_import(member.type, True)
                member_type_desc = member.type_string
                members.append((member_name, member_type, member_type_desc))

            self.add_str_to_types(indent, "@dataclass", 1)
            self.add_str_to_types(indent, f"class {self.get_name(struct.name)}:", 1)
            self.add_str_to_types(indent + 1, '"""', 1)
            self.add_str_to_types(indent + 1, "Attributes:", 1)
            for member_name, member_type, member_type_desc in members:
                self.add_str_to_types(
                    indent + 2, f"{member_name} ({member_type}): {member_type_desc}", 1
                )
            self.add_str_to_types(indent + 1, '"""', 1)

            for member_name, member_type, _ in members:
                self.add_str_to_types(indent + 1, f"{member_name}: {member_type}", 1)
            self.add_str_to_types(0, "", 2)

    # TODO very similar to generate_types_struct -> refactor
    def generate_types_enum(self, enums: Iterable[EnumDefinition], indent: int) -> None:
        self.__imports.add_python_import("from enum import IntEnum")
        for enum in enums:
            self.add_str_to_types(
                indent, f"class {self.get_name(enum.name)}(IntEnum):", 1
            )
            num = 0
            for member in enum.values:
                self.add_str_to_types(
                    indent + 1, self.get_name(member.name) + " = " + str(num), 1
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

            used_in = error.used_in[0]
            assert used_in.compilation_info is not None
            assert used_in.compilation_info.abi is not None

            error_abi = None

            for item in used_in.compilation_info.abi:
                if item["type"] == "error" and item["name"] == error.name:
                    selector = eth_utils.function_abi_to_4byte_selector(
                        item
                    )  # pyright: reportPrivateImportUsage=false
                    if selector == error.error_selector:
                        error_abi = item
                        break

            assert error_abi is not None

            parameters: List[Tuple[str, str, str]] = []
            unnamed_params_index = 1
            for parameter in error.parameters.parameters:
                if parameter.name:
                    parameter_name = self.get_name(parameter.name)
                else:
                    parameter_name = f"param{unnamed_params_index}"
                    unnamed_params_index += 1
                parameter_type = self.parse_type_and_import(parameter.type, True)
                parameter_type_desc = parameter.type_string
                parameters.append((parameter_name, parameter_type, parameter_type_desc))

            self.add_str_to_types(indent, "@dataclass", 1)
            self.add_str_to_types(
                indent,
                f"class {self.get_name(error.name)}(TransactionRevertedError):",
                1,
            )

            if len(parameters) > 0:
                self.add_str_to_types(indent + 1, '"""', 1)
                self.add_str_to_types(indent + 1, "Attributes:", 1)
                for param_name, param_type, param_type_desc in parameters:
                    self.add_str_to_types(
                        indent + 2, f"{param_name} ({param_type}): {param_type_desc}", 1
                    )
                self.add_str_to_types(indent + 1, '"""', 1)

            self.add_str_to_types(indent + 1, f"_abi = {error_abi}", 1)
            self.add_str_to_types(indent + 1, f"selector = {error.error_selector}", 2)
            for param_name, param_type, _ in parameters:
                self.add_str_to_types(indent + 1, f"{param_name}: {param_type}", 1)
            self.add_str_to_types(0, "", 2)

    def generate_types_event(
        self,
        events: Iterable[EventDefinition],
        indent: int,
        events_abi: Dict[bytes, Any],
    ) -> None:
        for event in events:
            parameters: List[Tuple[str, str, str]] = []
            unnamed_params_index = 1
            for parameter in event.parameters.parameters:
                if parameter.name:
                    parameter_name = self.get_name(parameter.name)
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
                parameters.append((parameter_name, parameter_type, parameter_type_desc))

            self.add_str_to_types(indent, "@dataclass", 1)
            self.add_str_to_types(indent, f"class {self.get_name(event.name)}:", 1)

            if len(parameters) > 0:
                self.add_str_to_types(indent + 1, '"""', 1)
                self.add_str_to_types(indent + 1, "Attributes:", 1)
                for param_name, param_type, param_type_desc in parameters:
                    self.add_str_to_types(
                        indent + 2, f"{param_name} ({param_type}): {param_type_desc}", 1
                    )
                self.add_str_to_types(indent + 1, '"""', 1)

            self.add_str_to_types(
                indent + 1, f"_abi = {events_abi[event.event_selector]}", 1
            )
            self.add_str_to_types(indent + 1, f"selector = {event.event_selector}", 2)
            for param_name, param_type, _ in parameters:
                self.add_str_to_types(indent + 1, f"{param_name}: {param_type}", 1)
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
                self.__imports.generate_contract_import_name(
                    parent.name, parent.parent.source_unit_name
                )
                return f"{self.get_name(parent.name)}.{self.get_name(expr.name)}"
            else:
                self.__imports.generate_struct_import(expr)
                return self.get_name(expr.name)
        elif isinstance(expr, types.Enum):
            parent = expr.ir_node.parent
            if isinstance(parent, ContractDefinition):
                self.__imports.generate_contract_import_name(
                    parent.name, parent.parent.source_unit_name
                )
                return f"{self.get_name(parent.name)}.{self.get_name(expr.name)}"
            else:
                self.__imports.generate_enum_import(expr)
                return self.get_name(expr.name)
        elif isinstance(expr, types.UserDefinedValueType):
            return self.parse_type_and_import(
                expr.ir_node.underlying_type.type, return_types
            )
        elif isinstance(expr, types.Array):
            return f"List[{self.parse_type_and_import(expr.base_type, return_types)}]"
        elif isinstance(expr, types.Contract):
            self.__imports.generate_contract_import_expr(expr)
            return self.get_name(expr.name)
        elif isinstance(expr, types.Mapping):
            self.__imports.add_python_import("from typing import Dict")
            return f"Dict[{self.parse_type_and_import(expr.key_type, return_types)}, {self.parse_type_and_import(expr.value_type, return_types)}]"
        else:
            return self.__sol_to_py_lookup[expr.__class__.__name__][types_index]

    def generate_func_params(
        self, fn: FunctionDefinition
    ) -> Tuple[List[Tuple[str, str]], List[str]]:
        params = []
        param_names = []
        unnamed_params_identifier: int = 1
        for par in fn.parameters.parameters:
            if not par.name:
                param_name: str = "arg" + str(unnamed_params_identifier)
                unnamed_params_identifier += 1
            else:
                param_name = par.name
            param_names.append((self.get_name(param_name), par.type_string))
            params.append(
                f"{self.get_name(param_name)}: {self.parse_type_and_import(par.type, False)}"
            )
        return param_names, params

    def generate_func_returns(self, fn: FunctionDefinition) -> List[Tuple[str, str]]:
        if len(fn.return_parameters.parameters) > 1:
            self.__imports.add_python_import("from typing import Tuple")
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
                    self.__imports.generate_contract_import_name(
                        parent.name, parent.parent.source_unit_name
                    )
                    return [
                        (
                            f"{self.get_name(parent.name)}.{self.get_name(struct.name)}",
                            struct_type_name.type_string,
                        )
                    ]
                else:
                    self.__imports.generate_struct_import(struct)
                    return [(self.get_name(struct.name), struct_type_name.type_string)]
            else:
                self.__imports.add_python_import("from typing import Tuple")
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
                        self.__imports.generate_contract_import_name(
                            parent.name, parent.parent.source_unit_name
                        )
                        parsed.append(
                            f"{self.get_name(parent.name)}.{self.get_name(var_type.name)}"
                        )
                    else:
                        self.__imports.generate_struct_import(var_type)
                        parsed.append(self.get_name(var_type.name))
                assert isinstance(var_type_name, UserDefinedTypeName)
                returns = get_struct_return_list(var_type_name)
            elif isinstance(var_type, types.Enum):
                parent = var_type.ir_node.parent
                if isinstance(parent, ContractDefinition):
                    self.__imports.generate_contract_import_name(
                        parent.name, parent.parent.source_unit_name
                    )
                    parsed.append(
                        f"{self.get_name(parent.name)}.{self.get_name(var_type.name)}"
                    )
                    returns = [
                        (
                            f"{self.get_name(parent.name)}.{self.get_name(var_type.name)}",
                            var_type_name.type_string,
                        )
                    ]

                else:
                    self.__imports.generate_enum_import(var_type)
                    parsed.append(self.get_name(var_type.name))
                    returns = [
                        (self.get_name(var_type.name), var_type_name.type_string)
                    ]
            elif isinstance(var_type, types.UserDefinedValueType):
                underlying_type = var_type.ir_node.underlying_type.type
                parsed.append(
                    self.__sol_to_py_lookup[underlying_type.__class__.__name__][0]
                )
                returns = [
                    (
                        self.__sol_to_py_lookup[underlying_type.__class__.__name__][1],
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
                assert isinstance(var_type_name, woke.ast.ir.type_name.mapping.Mapping)
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
                self.__imports.generate_contract_import_expr(var_type)
                returns = [(self.get_name(var_type.name), var_type_name.type_string)]
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
            decl.name, generated_params, returns_str, False
        )
        self.generate_type_hint_stub_func(
            decl.name, generated_params, f"LegacyTransaction[{returns_str}]", True
        )

        # getters never modify the state - passing VIEW is ok
        assert decl.function_selector is not None
        self.generate_func_implementation(
            StateMutability.VIEW,
            decl.canonical_name,
            decl.name,
            decl.function_selector.hex(),
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
        state_mutability: StateMutability,
        canonical_name: str,
        fn_name: str,
        fn_selector: str,
        params: List[str],
        param_names: List[Tuple[str, str]],
        returns: List[Tuple[str, str]],
    ):
        is_view_or_pure: bool = (
            state_mutability == StateMutability.VIEW
            or state_mutability == StateMutability.PURE
        )
        params_str = "".join(param + ", " for param in params)
        if len(returns) == 0:
            returns_str = None
        elif len(returns) == 1:
            returns_str = returns[0][0]
        else:
            returns_str = f"Tuple[{', '.join(ret[0] for ret in returns)}]"
        self.add_str_to_types(
            1,
            f"""def {self.get_name(fn_name)}(self, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, to: Optional[Union[Account, Address, str]] = None, value: int = 0, gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max", return_tx: bool = {False if is_view_or_pure else self.__return_tx_obj}, request_type: RequestType='{'call' if is_view_or_pure else 'default'}') -> Union[{returns_str}, LegacyTransaction[{returns_str}]]:""",
            1,
        )

        if len(param_names) + len(returns) > 0:
            self.add_str_to_types(2, '"""', 1)
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
            return_types = "type(None)"
        elif len(returns) == 1:
            return_types = returns[0][0]
        else:
            return_types = f"Tuple[{', '.join(map(itemgetter(0), returns))}]"
        self.add_str_to_types(
            2,
            f'return self._transact("{fn_selector}", [{", ".join(map(itemgetter(0), param_names))}], return_tx, request_type, {return_types}, from_, to, value, gas_limit) if not request_type == \'call\' else self._call("{fn_selector}", [{", ".join(map(itemgetter(0), param_names))}], return_tx, {return_types}, from_, to, value, gas_limit)',
            2,
        )

    def generate_type_hint_stub_func(
        self, fn_name: str, params: List[str], returns_str: str, return_tx: bool
    ):
        params_str = "".join(param + ", " for param in params)

        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(
            1,
            f"""def {self.get_name(fn_name)}(self, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, to: Optional[Union[Account, Address, str]] = None, value: int = 0, gas_limit: Union[int, Literal["max"], Literal["auto"]] = "max", return_tx: Literal[{return_tx}] = {return_tx}, request_type: RequestType='default') -> {returns_str}:""",
            1,
        )
        self.add_str_to_types(2, "...", 2)

    def generate_types_function(self, fn: FunctionDefinition):
        params_names, params = self.generate_func_params(fn)
        returns = self.generate_func_returns(fn)
        # the generated functions have parameter of type RequestType, which is an enum and must be imported
        self.__imports.add_python_import(
            "from woke.testing.pytypes_generator import RequestType"
        )

        if len(returns) == 0:
            returns_str = "None"
        elif len(returns) == 1:
            returns_str = returns[0][0]
        else:
            returns_str = f"Tuple[{', '.join(ret[0] for ret in returns)}]"

        self.generate_type_hint_stub_func(fn.name, params, returns_str, False)
        self.generate_type_hint_stub_func(
            fn.name, params, f"LegacyTransaction[{returns_str}]", True
        )

        assert fn.function_selector is not None
        self.generate_func_implementation(
            fn.state_mutability,
            fn.canonical_name,
            fn.name,
            fn.function_selector.hex(),
            params,
            params_names,
            returns,
        )

    def generate_types_contract(self, contract: ContractDefinition) -> None:
        if contract.name in self.__already_generated_contracts:
            return
        else:
            self.__already_generated_contracts.add(contract.name)
        inhertits_contract_class: bool = False if contract.base_contracts else True
        base_names: str = ""

        for base in reversed(contract.base_contracts):
            parent_contract = base.base_name.referenced_declaration
            assert isinstance(parent_contract, ContractDefinition)
            # only the types for contracts in the same source_unit are generated
            if (
                parent_contract.parent.source_unit_name
                == contract.parent.source_unit_name
            ):
                self.generate_types_contract(parent_contract)
                base_names += self.get_name(parent_contract.name) + ", "
            # contract is not in the same source unit, so it must be imported
            else:
                base_names += self.get_name(parent_contract.name) + ", "
                self.__imports.generate_contract_import_name(
                    parent_contract.name, parent_contract.parent.source_unit_name
                )

        if base_names:
            # remove trailing ", "
            base_names = base_names[:-2]
        if inhertits_contract_class:
            base_names = "Contract, " + base_names if base_names else "Contract"

        self.__imports.generate_default_imports = True
        events_abi = self.generate_contract_template(contract, base_names)

        if contract.enums:
            self.generate_types_enum(contract.enums, 1)

        if contract.structs:
            self.generate_types_struct(contract.structs, 1)

        if contract.errors:
            self.generate_types_error(contract.errors, 1)

        if contract.events:
            self.generate_types_event(contract.events, 1, events_abi)

        if contract.kind != ContractKind.LIBRARY:
            for var in contract.declared_variables:
                if (
                    var.visibility == Visibility.EXTERNAL
                    or var.visibility == Visibility.PUBLIC
                ):
                    self.generate_getter_for_state_var(var)
            for fn in contract.functions:
                if fn.function_selector:
                    self.generate_types_function(fn)

    def generate_types_source_unit(self, unit: SourceUnit) -> None:
        self.generate_types_struct(unit.structs, 0)
        self.generate_types_enum(unit.enums, 0)
        self.generate_types_error(unit.errors, 0)
        for contract in unit.contracts:
            self.generate_types_contract(contract)

    def clean_type_dir(self):
        """
        instead of recursive removal of type files inside pytypes dir
        remove the root and recreate it
        """
        if self.__pytypes_dir.exists():
            shutil.rmtree(self.__pytypes_dir)
        self.__pytypes_dir.mkdir(exist_ok=True)

    def write_source_unit_to_file(self, contract_name: str):
        self.__pytypes_dir.mkdir(exist_ok=True)
        contract_name = _make_path_alphanum(contract_name[:-3])
        unit_path = (self.__pytypes_dir / contract_name).with_suffix(".py")
        unit_path_parent = unit_path.parent
        # TODO validate whether project root can become paraent
        unit_path_parent.mkdir(parents=True, exist_ok=True)
        if unit_path.exists():
            with unit_path.open("a") as f:
                f.write(str(self.__imports) + self.__source_unit_types)
        else:
            unit_path.touch()
            unit_path.write_text(str(self.__imports) + self.__source_unit_types)

    # clean the instance variables to enable generating a new source unit
    def cleanup_source_unit(self):
        self.__source_unit_types = ""
        self.__imports.cleanup_imports()
        self.__already_generated_contracts = set()

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

    def generate_types(self, compilation_warnings: bool) -> None:
        # compile proj and generate ir
        self.run_compile(compilation_warnings)
        self.clean_type_dir()
        # self.traverse_funcs_to_check_overload()
        # print(self.__func_to_overload)
        for _, unit in self.__source_units.items():
            # print(f"source unit: {unit.source_unit_name}")
            self.__current_source_unit = unit.source_unit_name
            self.generate_types_source_unit(unit)
            self.write_source_unit_to_file(unit.source_unit_name)
            self.cleanup_source_unit()

        init_path = self.__pytypes_dir / "__init__.py"
        init_path.write_text(
            INIT_CONTENT.format(
                errors=self.__errors_index,
                events=self.__events_index,
                contracts_by_metadata=self.__contracts_by_metadata_index,
                contracts_inheritance=self.__contracts_inheritance_index,
                contracts_revert_index=self.__contracts_revert_index,
                deployment_code_index=self.__deployment_code_index,
            )
        )


class SourceUnitImports:
    __all_imports: str
    __struct_imports: Set[str]
    __enum_imports: Set[str]
    __contract_imports: Set[str]
    __python_imports: Set[str]
    __generate_default_imports: bool
    __type_gen: TypeGenerator

    def __init__(self, outer: TypeGenerator):
        self.__struct_imports = set()
        self.__enum_imports = set()
        self.__all_imports = ""
        self.__contract_imports = set()
        self.__python_imports = set()
        self.__generate_default_imports = False
        self.__type_gen = outer

    @property
    def generate_default_imports(self):
        return self.__generate_default_imports

    @generate_default_imports.setter
    def generate_default_imports(self, value: bool):
        self.__generate_default_imports = value

    def __str__(self) -> str:
        # __future__ has to be at the beginning of the file
        if "from __future__ import annotations" in self.__python_imports:
            self.add_str_to_imports(0, "from __future__ import annotations", 1)
            self.__python_imports.remove("from __future__ import annotations")

        if self.__generate_default_imports:
            self.add_str_to_imports(0, DEFAULT_IMPORTS, 1)

        for python_import in self.__python_imports:
            self.add_str_to_imports(0, python_import, 1)

        if self.__python_imports:
            self.add_str_to_imports(0, "", 1)

        for contract in self.__contract_imports:
            self.add_str_to_imports(0, contract, 1)

        if self.__contract_imports:
            self.add_str_to_imports(0, "", 1)

        for struct in self.__struct_imports:
            self.add_str_to_imports(0, struct, 1)

        if self.__struct_imports:
            self.add_str_to_imports(0, "", 1)

        if (
            self.generate_default_imports
            or self.__python_imports
            or self.__contract_imports
            or self.__struct_imports
        ):
            self.add_str_to_imports(0, "", 2)

        return self.__all_imports

    def cleanup_imports(self) -> None:
        self.__struct_imports = set()
        self.__enum_imports = set()
        self.__contract_imports = set()
        self.__python_imports = set()
        self.__all_imports = ""

    # TODO rename to better represent the functionality
    def generate_import(self, name: str, source_unit_name: str) -> str:
        source_unit_name = _make_path_alphanum(source_unit_name)
        return (
            "from pytypes."
            + source_unit_name[:-3].replace("/", ".")
            + " import "
            + self.__type_gen.get_name(name)
        )

    def add_str_to_imports(
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
        struct_import = self.generate_import(
            struct_type.name, source_unit.source_unit_name
        )

        if struct_import not in self.__struct_imports:
            # self.add_str_to_imports(0, struct_import, 1)
            self.__struct_imports.add(struct_import)

    # TODO impl of this func is basicaly the same as generate_struct_import -> refactor and remove duplication
    def generate_enum_import(self, enum_type: types.Enum):
        node = enum_type.ir_node
        if isinstance(node.parent, ContractDefinition):
            source_unit = node.parent.parent
        else:
            source_unit = node.parent
        # only those structs that are defined in a different source unit should be imported
        if source_unit.source_unit_name == self.__type_gen.current_source_unit:
            return
        enum_import = self.generate_import(enum_type.name, source_unit.source_unit_name)

        if enum_import not in self.__enum_imports:
            # self.add_str_to_imports(0, struct_import, 1)
            self.__struct_imports.add(enum_import)

    # TODO impl of this func is basicaly the same as generate_struct_import -> refactor and remove duplication
    def generate_contract_import_expr(self, contract_type: types.Contract):
        node = contract_type.ir_node
        source_unit = node.parent
        # only those contracts that are defined in a different source unit should be imported
        if source_unit.source_unit_name == self.__type_gen.current_source_unit:
            return

        contract_import = self.generate_import(
            contract_type.name, source_unit.source_unit_name
        )

        if contract_import not in self.__contract_imports:
            # self.add_str_to_imports(0, contract_import, 1)
            self.__contract_imports.add(contract_import)

    # TODO remove duplication
    def generate_contract_import_name(self, name: str, source_unit_name: str) -> None:
        # only those contracts that are defined in a different source unit should be imported
        if source_unit_name == self.__type_gen.current_source_unit:
            return

        contract_import = self.generate_import(name, source_unit_name)

        if contract_import not in self.__contract_imports:
            # self.add_str_to_imports(0, contract_import, 1)
            self.__contract_imports.add(contract_import)

    def add_python_import(self, p_import: str) -> None:
        self.__python_imports.add(p_import)


class NameSanitizer:
    __black_listed: Set[str]
    __used_names: Set[str]
    __renamed: Dict[str, str]

    def __init__(self):
        # TODO add names
        self.__black_listed = {
            "Dict",
            "List",
            "Mapping",
            "Set",
            "Tuple",
            "Union",
            "Path",
            "bytearray",
            "IntEnum",
            "dataclass",
            "Contract",
            "bytes",
            "map",
            "__str__",
            "__call__",
            "__init__",
            "_deploy",
            "_transact",
            "_call",
            "to",
            "from_",
            "value",
            "self",
            "deploy",
            "chain",
            "deployment_code",
        }
        self.__used_names = set()
        self.__renamed = {}

    def clean_names(self) -> None:
        self.__used_names = set()

    def sanitize_name(self, name: str) -> str:
        if name in self.__renamed:
            return self.__renamed[name]
        renamed = name
        while (
            renamed in self.__black_listed
            or renamed in self.__used_names
            or keyword.iskeyword(renamed)
        ):
            renamed = renamed + "_"
        self.__used_names.add(renamed)
        self.__renamed[name] = renamed
        return renamed
