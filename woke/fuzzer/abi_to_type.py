from __future__ import annotations

from abc import ABC
from ast import parse
import asyncio
from distutils.command import config
from distutils.command.clean import clean
from genericpath import exists
from multiprocessing.dummy import Array
from pathlib import Path, PurePath
from re import A
import shutil
from pathlib import Path, PurePath
import struct
from typing import Dict, List, Mapping, Set, Tuple, Union
from enum import Enum

import click
from click.core import Context
from intervaltree import IntervalTree
from rich.panel import Panel

import json
import keyword

from woke.ast.enums import *
from woke.ast.nodes import AstSolc
from woke.compile import SolcOutput, SolidityCompiler
from woke.compile.solc_frontend.input_data_model import SolcOutputSelectionEnum
from woke.config import WokeConfig

from ..ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.declaration.struct_definition import StructDefinition
from woke.ast.ir.declaration.enum_definition import EnumDefinition
from ..ast.ir.meta.source_unit import SourceUnit
from ..ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from ..ast.ir.utils import IrInitTuple
from ..cli.console import console
from woke.ast.enums import *

import woke.ast.expression_types as expr_types
from woke.ast.expression_types import ExpressionTypeAbc
from ..ast.ir.declaration.function_definition import FunctionDefinition
from ..compile.compilation_unit import CompilationUnit
from ..compile.solc_frontend import SolcOutputErrorSeverityEnum
from ..utils.file_utils import is_relative_to

from .constants import TAB_WIDTH, DEFAULT_IMPORTS


class RequestType(Enum):
  CALL = 'call'
  DEBUG = 'debug'
  TRACE = 'trace'
  DEFAULT = 'default' #default request type for the given network


class TypeGenerator():
    __config: WokeConfig
    #generated types for the given source unit
    __source_unit_types: str
    #set of contracts that were already generated in the given source unit
    #used to avoid generating the same contract multiple times, eg. when multiple contracts inherit from it
    __already_generated_contracts: Set[str]
    __source_units: Dict[Path, SourceUnit]
    #list of primitive types that the currently generated contract imports
    __imports: SourceUnitImports
    __name_sanitizer: NameSanitizer
    __current_source_unit: str
    __pytypes_dir: Path
    __sol_to_py_lookup: Dict[type, str]

    def __init__(
        self, config: WokeConfig):
        self.__config = config
        self.__source_unit_types = ""
        self.__already_generated_contracts = set()
        self.__source_units = {}
        self.__imports = SourceUnitImports(self)
        self.__name_sanitizer = NameSanitizer()
        self.__current_source_unit = ""
        self.__pytypes_dir = config.project_root_path / "pytypes"
        self.__sol_to_py_lookup = {}
        self.__init_sol_to_py_types()


    def __init_sol_to_py_types(self):
        self.__sol_to_py_lookup[expr_types.Address.__name__] = "AnyAddress"
        self.__sol_to_py_lookup[expr_types.String.__name__] = "str"
        self.__sol_to_py_lookup[expr_types.Array.__name__] = "arr"
        self.__sol_to_py_lookup[expr_types.Struct.__name__] = "struct"
        self.__sol_to_py_lookup[expr_types.Bool.__name__] = "bool"
        self.__sol_to_py_lookup[expr_types.Int.__name__] = "int"
        #self.__sol_to_py_lookup[expr_types.FixedBytes.__name__] = "fixed_bytes"
        self.__sol_to_py_lookup[expr_types.Bytes.__name__] = "bytearray"
        self.__sol_to_py_lookup[expr_types.Contract.__name__] = "contract"
        self.__sol_to_py_lookup[expr_types.Mapping.__name__] = "mapping"
        self.__sol_to_py_lookup[expr_types.UserDefinedValueType.__name__] = "user_defined"
        self.__sol_to_py_lookup[expr_types.Enum.__name__] = "enum"
        self.__sol_to_py_lookup[expr_types.Function.__name__] = "function"
        i: int = 8
        while i <= 256:
            #print("bytes" + str(i) + " = NewType(\"uint" + str(i) + "\", int)")
            self.__sol_to_py_lookup[expr_types.UInt.__name__ + str(i)] = "uint" + str(i)
            i += 8
        i = 1
        while i <= 32:
            #print("bytes" + str(i) + " = NewType(\"bytes" + str(i) + "\", bytearray)")
            self.__sol_to_py_lookup[expr_types.FixedBytes.__name__ + str(i)] = "bytes" + str(i)
            i += 1

    @property
    def current_source_unit(self):
        return self.__current_source_unit


    def run_compile(self, parse=True
    ) -> None:
        """Compile the project."""
        sol_files: Set[Path] = set()
        for file in self.__config.project_root_path.rglob("**/*.sol"):
            if (
                    not any(is_relative_to(file, p) for p in self.__config.compiler.solc.ignore_paths)
                    and file.is_file()
            ):
                sol_files.add(file)

        compiler = SolidityCompiler(self.__config)
        # TODO Allow choosing build artifacts subset in compile subcommand
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
                if error.formatted_message is not None:
                    console.print(Panel(error.formatted_message, highlight=True))
                else:
                    console.print(Panel(error.message, highlight=True))

        if errored:
            raise Exception("Compilation failed")

        processed_files: Set[Path] = set()
        reference_resolver = ReferenceResolver()
        interval_trees: Dict[Path, IntervalTree] = {}

        for cu, output in outputs:
            for source_unit_name, info in output.sources.items():
                path = cu.source_unit_name_to_path(PurePath(source_unit_name))

                interval_trees[path] = IntervalTree()
                ast = AstSolc.parse_obj(info.ast)

                reference_resolver.index_nodes(ast, path, cu.hash)

                if path in processed_files:
                    continue
                processed_files.add(path)

                assert source_unit_name in output.contracts

                init = IrInitTuple(
                    path,
                    path.read_bytes(),
                    cu,
                    interval_trees[path],
                    reference_resolver,
                    output.contracts[source_unit_name],
                )
                self.__source_units[path] = SourceUnit(init, ast)

        reference_resolver.run_post_process_callbacks(
            CallbackParams(source_units=self.__source_units)
    )


    def add_str_to_types(self, num_of_indentation: int, string: str, num_of_newlines: int): 
        self.__source_unit_types += num_of_indentation * TAB_WIDTH * ' ' + string + num_of_newlines * '\n'

    def get_name(self, name: str) -> str:
        return self.__name_sanitizer.sanitize_name(name)

    def generate_contract_template(self, contract: ContractDefinition, base_names: str) -> None:
        self.add_str_to_types(0, "class " + self.get_name(contract.name) + "(" + base_names + "):", 1)
        compilation_info = contract.compilation_info
        if compilation_info.abi:
            self.add_str_to_types(1, f"abi = {compilation_info.abi}", 1)
        if compilation_info.abi and compilation_info.evm.bytecode.opcodes: 
            self.add_str_to_types(1, f"bytecode = \"{compilation_info.evm.bytecode.object}\"", 2)

        self.__imports.add_python_import("from __future__ import annotations")
        self.add_str_to_types(1, "@classmethod", 1)
        self.add_str_to_types(1, f"def deploy(cls, params: Optional[TxParams] = None) -> {contract.name}:", 1)
        self.add_str_to_types(2, "return super().deploy(params)", 1)
        #if compilation_info.
        self.add_str_to_types(0, "", 1)


    def generate_types_enum(self, contract: ContractDefinition) -> None:
        enums = contract.enums


    def generate_types_struct(self, structs: List[StructDefinition], indent: int) -> None:
        for struct in structs:
            self.add_str_to_types(indent, "@dataclass", 1)
            self.add_str_to_types(indent, f"class {self.get_name(struct.name)}:", 1)
            for member in struct.members:
                self.add_str_to_types(indent + 1, self.get_name(member.name) + ": " + self.parse_type_and_import(member.type), 1)
            self.add_str_to_types(0, "", 2) 


    #TODO very similar to generate_types_struct -> refactor
    def generate_types_enum(self, enums: List[EnumDefinition], indent: int) -> None:
        self.__imports.add_python_import("from enum import IntEnum")
        for enum in enums:
            self.add_str_to_types(indent, f"class {self.get_name(enum.name)}(IntEnum):", 1)
            num = 0
            for member in enum.values:
                self.add_str_to_types(indent + 1, self.get_name(member.name) + " = " + str(num), 1)
                num += 1
            self.add_str_to_types(0, "", 2) 


    #parses the expr to string
    #optionaly generates an import
    def parse_type_and_import(self, expr: ExpressionTypeAbc) -> str:
        name = expr.__class__.__name__
        parsed: str = ""
        if name == "Struct":
            parsed += self.get_name(expr.name)
            self.__imports.generate_struct_import(expr)
        elif name == "Array":
            parsed += "List[" + self.parse_type_and_import(expr.base_type) + "]"
        elif name == "UInt":
            self.__imports.add_primitive_type(self.__sol_to_py_lookup[name + str(expr.bits_count)])
            parsed += self.__sol_to_py_lookup[name + str(expr.bits_count)]
        elif name == "FixedBytes":
            self.__imports.add_primitive_type(self.__sol_to_py_lookup[name + str(expr.bytes_count)])
            parsed += self.__sol_to_py_lookup[name + str(expr.bytes_count)]
        elif name == "Contract":
            parsed += self.get_name(expr.name)
            self.__imports.generate_contract_import_expr(expr)
        elif name == "Mapping":
            self.__imports.add_python_import("from typing import Dict")
            parsed += f"Dict[{self.parse_type_and_import(expr.key_type)}, {self.parse_type_and_import(expr.value_type)}]"
        elif name == "Enum":
            parsed += self.get_name(expr.name)
            self.__imports.generate_enum_import(expr)
        else:
            parsed += self.__sol_to_py_lookup[name]
        return parsed


    def generate_func_params(self, fn: FunctionDefinition) -> Tuple[str, str]:
        params: str = ""
        #params_names are later inserted as an argument to the self.transact call
        params_names: str = ""
        for par in fn.parameters.parameters:
            params_names += self.get_name(par.name) + ", "
            params += self.get_name(par.name) + ": " + self.parse_type_and_import(par.type) + ", "
        params += "params: Optional[TxParams] = None"
        if params_names:
            return params_names[:-2], params
        return params_names, params


    def generate_func_returns(self, fn: FunctionDefinition) -> str:
        return_params: str = ""
        for ret in fn.return_parameters.parameters:
            return_params += self.parse_type_and_import(ret.type) + ", "
        if return_params:
            #return and remove the trailing comma ", "
            return return_params[:-2]
        else:
            return return_params + "None"

    #generates undeployable contract - interafaces and abstract contracts
    def generate_types_interface(self, contract: ContractDefinition) -> None:
        if contract.structs:
            self.__imports.add_python_import("from dataclasses import dataclass")
        self.add_str_to_types(0, "class " + self.get_name(contract.name) + "():", 1)
        if not contract.structs:
            self.add_str_to_types(1, "pass" , 1)


    #TODO ensure that making the path alphanum wont create collisions
    def make_path_alphanum(self, path: str) -> str:
        return ''.join(filter(lambda ch: ch.isalnum() or ch == '/' or ch == '_', path))

    
    def is_compound_type(self, var_type: ExpressionTypeAbc):
        name = var_type.__class__.__name__
        return name ==  "Array" or name == "Mapping"

    def generate_getter_for_state_var(self, decl: VariableDeclaration):

        def get_struct_return_list(struct: expr_types.Struct) -> str:
            node = struct.ir_node
            assert isinstance(node, StructDefinition)
            non_exluded = []
            for member in node.members:
                if not isinstance(member.type, expr_types.Mapping) and not isinstance(member.type, expr_types.Array):
                    non_exluded.append(self.parse_type_and_import(member.type))
            if len(node.members) == len(non_exluded):
                #nothing was exluded -> the whole struct will be used -> add the struct to imports
                self.__imports.generate_struct_import(struct)
                return self.get_name(struct.name)
            else:
                self.__imports.add_python_import("from typing import Tuple")
                return "Tuple[" + ", ".join(non_exluded) + "]"


        returns: str = ""
        param_names: str = ""
        #if the type is compound we need to use the type as an index, for primitive types we use the
        #the type only for the return
        #TODO reorder the elif chain such that the most common types are on the top
        def generate_getter_helper(var_type: ExpressionTypeAbc, use_parse: bool, depth: int) -> str:
            nonlocal returns
            nonlocal param_names
            name = var_type.__class__.__name__
            parsed: str = ""
            if name == "Struct":
                if depth == 0:
                    parsed += ""
                else:
                    parsed += self.get_name(var_type.name)
                    self.__imports.generate_struct_import(var_type)
                returns = get_struct_return_list(var_type)
            elif name == "Array":
                #parsed += "List[" + generate_function(var_type.base_type, True) + "]"
                use_parse = True
                param_names += "index" + str(depth) + ", "
                if self.is_compound_type(var_type.base_type):
                    parsed += "index" + str(depth) + ": uint256" + ", " + generate_getter_helper(var_type.base_type, True, depth + 1)
                else:
                    parsed += "index" + str(depth) + ": uint256"
                    #ignores the parsed return, only called for the side-effect of changing the returns var to value_type
                    _ = generate_getter_helper(var_type.base_type, False, depth + 1)
            elif name == "Mapping":
                #parse key
                use_parse = True
                param_names += "key" + str(depth) + ", "
                parsed += "key" + str(depth) + ": " + generate_getter_helper(var_type.key_type, True, depth + 1)
                if self.is_compound_type(var_type.value_type):
                    parsed += ", " + generate_getter_helper(var_type.value_type, True, depth + 1)
                else:
                    #ignores the parsed return, only called for the side-effect of changing the returns var to value_type
                    _ = generate_getter_helper(var_type.value_type, True, depth + 1)
            elif name == "UInt":
                self.__imports.add_primitive_type(self.__sol_to_py_lookup[name + str(var_type.bits_count)])
                parsed += self.__sol_to_py_lookup[name + str(var_type.bits_count)]
                returns =  self.__sol_to_py_lookup[name + str(var_type.bits_count)]
            elif name == "FixedBytes":
                self.__imports.add_primitive_type(self.__sol_to_py_lookup[name + str(var_type.bytes_count)])
                parsed +=  self.__sol_to_py_lookup[name + str(var_type.bytes_count)]
                returns =  self.__sol_to_py_lookup[name + str(var_type.bytes_count)]
            elif name == "Contract":
                self.__imports.generate_contract_import_expr(var_type)
                returns =  self.get_name(var_type.name)
            else:
                parsed += self.__sol_to_py_lookup[name]
                returns = self.__sol_to_py_lookup[name]

            return parsed if use_parse else ""

        generated_params = generate_getter_helper(decl.type, False, 0)
        generated_params = generated_params + ", params: Optional[TxParams] = None" if generated_params else "params: Optional[TxParams] = None"

        self.generate_type_hint_stub_func(decl.name, generated_params, returns, False)
        self.generate_type_hint_stub_func(decl.name, generated_params, "TransactionObject", True)

        #getters never modify the state - passing VIEW is ok
        self.generate_func_implementation(StateMutability.VIEW, decl.name, decl.function_selector.hex(), generated_params, param_names, returns)

        if param_names:
            param_names = param_names[:-2]
        #self.add_str_to_types(1, f"def {self.get_name(decl.name)}({generated_params}) -> {returns if returns else 'None'}:", 1)
        #self.add_str_to_contract_types(2, "pass" + " " + param_names, 2) 
        #print(decl.function_selector[3:].decode("utf-8"))
        #self.add_str_to_types(2, "return self.transact(\"" + decl.function_selector.hex() + '\", [' + param_names + ']' + ", params)", 2)
        #print(self.__contract_types)

    def generate_func_implementation(self, state_mutability: StateMutability, fn_name: str, fn_selector: str, params: str, param_names: str, returns: str):
        #default value whether to return tx or the return data - if the function is pure/view the default is to make only a call and return the return data
        is_view_or_pure: bool = state_mutability == StateMutability.VIEW or state_mutability == StateMutability.PURE
        self.add_str_to_types(1, f"def {self.get_name(fn_name)}(self, {params}, return_tx: bool=False, request_type: RequestType='{'call' if is_view_or_pure else 'default'}') -> Union[{returns}, TransactionObject]:", 1)
        self.add_str_to_types(2, f"return self.transact(\"{fn_selector}\", [{param_names}], params, return_tx, request_type) if not return_tx == 'call' else self.call(\"{fn_selector}\", [{param_names}], params, return_tx)", 2)


    def generate_type_hint_stub_func(self, fn_name: str, params: str, returns: str, return_tx: bool):
        self.add_str_to_types(1, "@overload", 1)
        self.add_str_to_types(1, f"def {self.get_name(fn_name)}(self, {params}, return_tx: bool={return_tx}, request_type: RequestType='default') -> {returns}:", 1)
        self.add_str_to_types(2, "...", 2)


    def generate_types_function(self, fn: FunctionDefinition):
        params_names, params = self.generate_func_params(fn)
        returns = self.generate_func_returns(fn)
        self.generate_type_hint_stub_func(fn.name, params, returns, False)
        self.generate_type_hint_stub_func(fn.name, params, "TransactionObject", True)

        self.generate_func_implementation(fn.state_mutability, fn.name, fn.function_selector.hex(), params, params_names, returns)
        #gs_view_or_pure: bool = fn.state_mutability == StateMutability.VIEW or fn.state_mutability == StateMutability.PURE
        #gelf.add_str_to_types(1, f"def {self.get_name(fn.name)}(self{params}, return_tx: bool={True if is_view_or_pure else False}) -> Union[{returns}, TransactionObject]:", 1)
        #self.add_str_to_types(2, f"return self.transact(\"{fn.function_selector.hex()}\", [{params_names}], params) if return_tx else self.call(\"{fn.function_selector.hex()}\", [{params_names}], params)", 3)


    def generate_types_contract(self, contract: ContractDefinition, generate_template: bool) -> None:
        if contract.name in self.__already_generated_contracts:
            return
        else:
            self.__already_generated_contracts.add(contract.name)
        #bool indicating whether the given contract should inherit from Contract class
        inhertits_contract: bool = contract.kind == ContractKind.CONTRACT and not contract.abstract
        base_names: str = ""

        for base in contract.base_contracts:
            parent_contract: ContractDefinition = base.base_name.referenced_declaration
            #only the types for contracts in the same source_unit are generated
            if parent_contract.parent.source_unit_name == contract.parent.source_unit_name:
                if parent_contract.kind == ContractKind.CONTRACT and not parent_contract.abstract:
                    inhertits_contract = False
                    self.generate_types_contract(parent_contract, True)
                    base_names += self.get_name(parent_contract.name) + ", "
                elif parent_contract.kind == ContractKind.INTERFACE and parent_contract.structs:
                    #TODO will nevever inherit from Contract, will probably not need template (aka imports)
                    #will only be generated to contain the user defined types
                    self.generate_types_interface(parent_contract, False)
                elif parent_contract.kind == ContractKind.CONTRACT and parent_contract.abstract and parent_contract.structs:
                    self.generate_types_undeployable_contract(parent_contract, False)
                    base_names += self.get_name(parent_contract.name) + ", "
            else:
                base_names += self.get_name(parent_contract.name) + ", "
                self.__imports.generate_contract_import_name(parent_contract.name, parent_contract.parent.source_unit_name)
            if parent_contract.kind == ContractKind.CONTRACT and not parent_contract.abstract:
                inhertits_contract = False

        if base_names:
            #remove trailing ", "
            base_names = base_names[:-2] 
        if inhertits_contract:
            base_names = "Contract, " + base_names if base_names else "Contract"

        #TODO generate template only if the given contract file (as specified by its canonical name)
        #doesn't contain anything - some other contract might have been already stored to that file
        #TODO add imports of inherited contracts
        if generate_template:
            self.__imports.generate_default_imports = True
            self.generate_contract_template(contract, base_names)
        if contract.kind == ContractKind.INTERFACE:
            self.generate_types_interface(contract)

        if contract.enums:
            self.generate_types_enum(contract.enums, 1)

        if contract.structs:
            self.generate_types_struct(contract.structs, 1)

        if contract.kind == ContractKind.CONTRACT and not contract.abstract or contract.kind == ContractKind.LIBRARY:
            for var in contract.declared_variables:
                if var.visibility == Visibility.EXTERNAL or var.visibility == Visibility.PUBLIC:
                    self.generate_getter_for_state_var(var)
            for fn in contract.functions:
                if fn.function_selector:
                    self.generate_types_function(fn)
                    
            for variable in contract.declared_variables:
                if isinstance(variable.type_name, Mapping):
                    variable.type


    def generate_types_source_unit(self, unit: SourceUnit) -> None:
        self.generate_types_struct(unit.structs, 0)
        self.generate_types_enum(unit.enums, 0)
        for contract in unit.contracts:
            if contract.kind == ContractKind.CONTRACT and not contract.abstract:
                self.generate_types_contract(contract, True)
            elif contract.kind == ContractKind.LIBRARY:
                continue
            elif contract.kind == ContractKind.INTERFACE:
                self.generate_types_contract(contract, False)


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
        contract_name = self.make_path_alphanum(contract_name[:-3])
        unit_path = (self.__pytypes_dir / contract_name).with_suffix(".py")
        unit_path_parent = unit_path.parent
        #TODO validate whether project root can become paraent
        unit_path_parent.mkdir(parents=True,exist_ok=True)
        if unit_path.exists():
            with unit_path.open('a') as f:
                f.write(str(self.__imports) + self.__source_unit_types)
        else:
            unit_path.touch()
            unit_path.write_text(str(self.__imports) + self.__source_unit_types)


    #clean the instance variables to enable generating a new source unit
    def cleanup_source_unit(self):
        self.__source_unit_types = ""
        self.__imports.cleanup_imports()
        self.__already_generated_contracts = set()


    def mark_funcs_to_be_overloaded(self):
        #set containing canonical names of functions to be overloaded
        to_overload: Set[str] = set()
        for _, unit in self.__source_units.items():
            pass

    def generate_types(self, overwrite: bool = False) -> None:
        #compile proj and generate ir
        #TODO fail if any compile erors
        self.run_compile() 
        self.clean_type_dir()
        for _, unit in self.__source_units.items():
            self.__current_source_unit = unit.source_unit_name
            self.generate_types_source_unit(unit)
            self.write_source_unit_to_file(unit.source_unit_name)
            self.cleanup_source_unit()


class SourceUnitImports():
    __used_primitive_types: Set[str]
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
        self.__used_primitive_types = set()
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
        #__future__ has to be at the beginning of the file
        if "from __future__ import annotations" in self.__python_imports:
            self.add_str_to_imports(0, "from __future__ import annotations", 1)
            self.__python_imports.remove("from __future__ import annotations")

        if self.__generate_default_imports:
            self.add_str_to_imports(0, DEFAULT_IMPORTS, 1)

        for python_import in self.__python_imports:
            self.add_str_to_imports(0, python_import, 1)

        if self.__python_imports:
            self.add_str_to_imports(0,"", 1) 

        for contract in self.__contract_imports:
            self.add_str_to_imports(0, contract, 1)

        if self.__contract_imports:
            self.add_str_to_imports(0,"", 1) 

        for struct in self.__struct_imports:
            self.add_str_to_imports(0, struct, 1)

        if self.__struct_imports:
            self.add_str_to_imports(0,"", 1) 

        #TODO add to one import statement to avoid having multiple lines of imports from the same file
        for p_type in self.__used_primitive_types:
            self.add_str_to_imports(0, "from woke.fuzzer.primitive_types import " + p_type, 1)
        
        if self.generate_default_imports or self.__python_imports or self.__contract_imports or self.__struct_imports or self.__used_primitive_types:
            self.add_str_to_imports(0,"", 2) 

        return self.__all_imports


    def cleanup_imports(self) -> None:
        self.__struct_imports = set()
        self.__enum_imports = set()
        self.__contract_imports = set()
        self.__used_primitive_types = set()
        self.__python_imports = set()
        self.__all_imports = ""


    #TODO rename to better represent the functionality
    def generate_import(self, name: str, source_unit_name: str) -> str:
        source_unit_name = self.make_path_alphanum(source_unit_name)
        return  "from pytypes." + source_unit_name[:-3].replace('/', '.') + " import " + name


    def add_str_to_imports(self, num_of_indentation: int, string: str, num_of_newlines: int): 
        self.__all_imports += num_of_indentation * TAB_WIDTH * ' ' + string + num_of_newlines * '\n'


    def generate_struct_import(self, expr: ExpressionTypeAbc):
        node  = expr.ir_node
        if isinstance(node.parent, ContractDefinition):
            source_unit = node.parent.parent
        else:
            source_unit = node.parent
        #only those structs that are defined in a different source unit should be imported
        if source_unit.source_unit_name == self.__type_gen.current_source_unit:
            return 
        struct_import = self.generate_import(expr.name, source_unit.source_unit_name)

        if struct_import not in self.__struct_imports:
            #self.add_str_to_imports(0, struct_import, 1) 
            self.__struct_imports.add(struct_import)


    #TODO impl of this func is basicaly the same as generate_struct_import -> refactor and remove duplication
    def generate_enum_import(self, expr: ExpressionTypeAbc):
        node  = expr.ir_node
        if isinstance(node.parent, ContractDefinition):
            source_unit = node.parent.parent
        else:
            source_unit = node.parent
        #only those structs that are defined in a different source unit should be imported
        if source_unit.source_unit_name == self.__type_gen.current_source_unit:
            return 
        enum_import = self.generate_import(expr.name, source_unit.source_unit_name)

        if enum_import not in self.__enum_imports:
            #self.add_str_to_imports(0, struct_import, 1) 
            self.__struct_imports.add(enum_import)


    #TODO impl of this func is basicaly the same as generate_struct_import -> refactor and remove duplication
    def generate_contract_import_expr(self, expr: ExpressionTypeAbc):
        node: ContractDefinition  = expr.ir_node
        source_unit = node.parent
        #only those contracts that are defined in a different source unit should be imported
        if source_unit.source_unit_name == self.__type_gen.current_source_unit:
            return 

        contract_import = self.generate_import(expr.name, source_unit.source_unit_name)

        if contract_import not in self.__contract_imports:
            #self.add_str_to_imports(0, contract_import, 1) 
            self.__contract_imports.add(contract_import)


    #TODO remove duplication
    def generate_contract_import_name(self, name: str, source_unit_name: str) -> None:
        contract_import = self.generate_import(name, source_unit_name)

        if contract_import not in self.__contract_imports:
            #self.add_str_to_imports(0, contract_import, 1) 
            self.__contract_imports.add(contract_import)

    def add_primitive_type(self, primitive_type: str) -> None:
        self.__used_primitive_types.add(primitive_type)


    def add_python_import(self, p_import: str) -> None:
        self.__python_imports.add(p_import)


    def make_path_alphanum(self, path: str) -> str:
        return ''.join(filter(lambda ch: ch.isalnum() or ch == '/' or ch == '_', path))


class NameSanitizer():
    __black_listed: Set[str]
    __used_names: Set[str]
    __renamed: Dict[str, str]

    def __init__(self):
        #TODO add names
        self.__black_listed = {"Dict", "List", "Mapping", "Set", "Tuple", "Union", "Path", "bytearray", "deploy", "IntEnum", "dataclass", "Contract", "bytes", "map", "__str__", "__call__", "__init__", "transact"}
        self.__used_names = set()
        self.__renamed = {}


    def clean_names(self) -> None:
        self.__used_names = set()


    def sanitize_name(self, name: str) -> str:
        if name in self.__renamed:
            return self.__renamed[name]
        renamed = name
        while renamed in self.__black_listed or renamed in self.__used_names or keyword.iskeyword(renamed):
            renamed = renamed + '_'
        self.__used_names.add(renamed)
        self.__renamed[name] = renamed
        return renamed