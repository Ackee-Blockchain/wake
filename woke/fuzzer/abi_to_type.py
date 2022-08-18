from abc import ABC
from ast import parse
import asyncio
from distutils.command import config
from distutils.command.clean import clean
from genericpath import exists
from pathlib import Path, PurePath
from re import A
import shutil
import string
from pathlib import Path, PurePath
import struct
from typing import Dict, List, Mapping, Set, Tuple
from unicodedata import name

import click
from click.core import Context
from intervaltree import IntervalTree
from rich.panel import Panel

from woke.ast.enums import *
from woke.ast.nodes import AstSolc
from woke.compile import SolcOutput, SolidityCompiler
from woke.compile.solc_frontend.input_data_model import SolcOutputSelectionEnum
from woke.config import WokeConfig

from ..ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.declaration.struct_definition import StructDefinition
from ..ast.ir.meta.source_unit import SourceUnit
from ..ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from ..ast.ir.utils import IrInitTuple
from ..cli.console import console
from woke.ast.enums import *
from woke.utils.string import StringReader

import woke.ast.expression_types as expr_types
from woke.ast.expression_types import ExpressionTypeAbc
from ..ast.ir.declaration.function_definition import FunctionDefinition
from ..compile.compilation_unit import CompilationUnit
from ..compile.solc_frontend import SolcOutputErrorSeverityEnum
from ..utils.file_utils import is_relative_to


#tab space width for indentation
TAB_WIDTH = 4

DEFAULT_IMPORTS: str = """
import random 
from dataclasses import dataclass 
from typing import List, NewType, Optional

from woke.fuzzer.contract import Contract

from eth_typing import AnyAddress, HexStr
from web3 import Web3, WebsocketProvider, HTTPProvider
from web3.method import Method
from web3.types import TxParams, Address, RPCEndpoint
"""

class TypeGenerator():
    __config: WokeConfig
    #generated types for the given source unit
    __source_unit_types: str
    __source_units: Dict[Path, SourceUnit]
    #list of primitive types that the currently generated contract imports
    #used  to generate import strings
    __used_primitive_types: Set[str]
    #holds all imports for the given source unit
    __source_unit_imports: Set[str]
    __pytypes_dir: Path
    __sol_to_py_lookup: Dict[type, str]
    __default_imports_generated: bool

    def __init__(
        self, config: WokeConfig):
        self.__config = config
        self.__source_unit_types = ""
        self.__source_units = {}
        self.__used_primitive_types = set()
        self.__source_unit_imports = ""
        self.__pytypes_dir = config.project_root_path / "pytypes"
        self.__sol_to_py_lookup = {}
        self.__default_imports_generated = False
        self.__init_sol_to_py_types()


    def __init_sol_to_py_types(self):
        self.__sol_to_py_lookup[expr_types.Address.__name__] = "AnyAddress"
        self.__sol_to_py_lookup[expr_types.String.__name__] = "str"
        self.__sol_to_py_lookup[expr_types.Array.__name__] = "arr"
        self.__sol_to_py_lookup[expr_types.Struct.__name__] = "struct"
        self.__sol_to_py_lookup[expr_types.Bool.__name__] = "bool"
        self.__sol_to_py_lookup[expr_types.Int.__name__] = "int"
        #self.__sol_to_py_lookup[expr_types.FixedBytes.__name__] = "fixed_bytes"
        self.__sol_to_py_lookup[expr_types.Bytes.__name__] = "bytes"
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


    def write_contract_types_to_file(self, contract_name: str):
        self.__pytypes_dir.mkdir(exist_ok=True)
        contract_name = self.make_path_alphanum(contract_name[:-3])
        unit_path = (self.__pytypes_dir / contract_name).with_suffix(".py")
        unit_path_parent = unit_path.parent
        #TODO validate whether project root can become paraent
        unit_path_parent.mkdir(parents=True,exist_ok=True)
        if unit_path.exists():
            with unit_path.open('a') as f:
                f.write(self.__source_unit_types)
        else:
            unit_path.touch()
            unit_path.write_text(self.__source_unit_types)


    def add_str_to_contract_types(self, num_of_indentation: int, string: str, num_of_newlines: int): 
        self.__source_unit_types += num_of_indentation * TAB_WIDTH * ' ' + string + num_of_newlines * '\n'


    def add_str_to_contract_imports(self, num_of_indentation: int, string: str, num_of_newlines: int): 
        self.__source_unit_imports += num_of_indentation * TAB_WIDTH * ' ' + string + num_of_newlines * '\n'


    def generate_contract_template(self, contract: ContractDefinition, base_names: str, base_imports: str):
        if not self.__default_imports_generated:
            self.add_str_to_contract_imports(0, DEFAULT_IMPORTS, 1)
        self.__default_imports_generated = True
        self.add_str_to_contract_imports(0, base_imports, 2)

        self.add_str_to_contract_types(0, "class " + contract.name + "(" + base_names + "):", 1)
        #TODO add abi
        self.add_str_to_contract_types(1, "abi = json.loads(TODO)", 1)
        #TODO add bytecode
        self.add_str_to_contract_types(1, "bytecode = TODO", 1)
        self.add_str_to_contract_types(0, "", 1)


    def generate_types_enum(self, contract: ContractDefinition) -> None:
        enums = contract.enums


    def generate_types_struct(self, structs: List[StructDefinition]) -> None:
        for struct in structs:
            self.add_str_to_contract_types(1, "@dataclass", 1)
            self.add_str_to_contract_types(1, f"class {struct.name}:", 1)
            for member in struct.members:
                self.add_str_to_contract_types(2, member.canonical_name.split('.')[-1] + ": " + self.parse_type(member.type), 1)
            self.add_str_to_contract_types(0, "", 2)


    def parse_type(self, var_type: ExpressionTypeAbc) -> str:
        name = var_type.__class__.__name__
        parsed: str = ""
        if name == "Struct":
            parsed += var_type.name
        elif name == "Array":
            #TODO implement nested arrays
            #parsed = "List[" + var_type.base_type.__class__.__name__ + "]"
            parsed += "List[" + self.parse_type(var_type.base_type) + "]"
        elif name == "UInt":
            self.__used_primitive_types.add(self.__sol_to_py_lookup[name + str(var_type.bits_count)])
            parsed += self.__sol_to_py_lookup[name + str(var_type.bits_count)]
        elif name == "FixedBytes":
            self.__used_primitive_types.add(self.__sol_to_py_lookup[name + str(var_type.bytes_count)])
        else:
            parsed += self.__sol_to_py_lookup[name]
        return parsed


    def generate_func_params(self, fn: FunctionDefinition) -> Tuple[str, str]:
        params: str = ""
        #params_names are later inserted as an argument to the self.transact call
        params_names: str = ""
        for par in fn.parameters.parameters:
            params_names += par.name + ", "
            params += ", " + par.name + ": " + self.parse_type(par.type)
        params += ", params: Optional[TxParams] = None"
        if params_names:
            return params_names[:-2], params
        return params_names, params


    def generate_func_returns(self, fn: FunctionDefinition) -> str:
        return_params: str = ""
        for ret in fn.return_parameters.parameters:
            return_params += self.parse_type(ret.type) + ", "
        if return_params:
            return return_params[:-2]
        else:
            return return_params + "None"


    #generates undeployable contract - interafaces and abstract contracts
    def generate_types_interface(self, contract: ContractDefinition, generate_template: bool) -> None:
        self.add_str_to_contract_types(0, "from dataclasses import dataclass", 2)
        self.add_str_to_contract_types(0, "class " + contract.name + "():", 1)
        self.generate_types_struct(contract.structs)  
        self.write_contract_types_to_file(contract.parent.source_unit_name)
        self.__source_unit_types = ""


    #TODO ensure that stripping the path wont create collisions
    #either 
    def make_path_alphanum(self, path: str) -> str:
        return ''.join(filter(lambda ch: ch.isalnum() or ch == '/' or ch == '_', path))

    #TODO rename to better represent the functionality
    def generate_import(self, name: str, source_unit_name: str) -> str:
        source_unit_name = self.make_path_alphanum(source_unit_name)
        return  "from pytypes." + source_unit_name[:-3].replace('/', '.') + " import " + name + "\n"


    def generate_primitive_imports(self):
        for p_type in self.__used_primitive_types:
            #print(self.__source_unit_imports)
            self.add_str_to_contract_imports(0, "from woke.fuzzer.primitive_types import " + p_type, 1)
        
        self.add_str_to_contract_imports(0,"", 1) 


    def is_compound_type(self, var_type: ExpressionTypeAbc):
        name = var_type.__class__.__name__
        return name ==  "Array" or name == "Mapping"


    def generate_func_from_instance_var(self, decl: VariableDeclaration):
        returns: str = ""
        param_names: str = ""
        #if the type is compound we need to use the type as an index, for primitive types we use the
        #the type only for the return
        def generate_function(var_type: ExpressionTypeAbc, use_parse: bool, depth: int) -> str:
            nonlocal returns
            nonlocal param_names
            name = var_type.__class__.__name__
            parsed: str = ""
            if name == "Struct":
                parsed += var_type.name
            elif name == "Array":
                #parsed += "List[" + generate_function(var_type.base_type, True) + "]"
                param_names += "index" + str(depth) + ", "
                if self.is_compound_type(var_type.base_type):
                    parsed += "index" + str(depth) + ": uint256" + ", " + generate_function(var_type.base_type, True, depth + 1)
                else:
                    parsed += "index" + str(depth) + ": uint256"
                    #ignores the parsed return, only called for the side-effect of changing the returns var to value_type
                    _ = generate_function(var_type.base_type, False, depth + 1)
            elif name == "Mapping":
                #parse key
                param_names += "key" + str(depth) + ", "
                parsed += "key" + str(depth) + ": " + generate_function(var_type.key_type, True, depth + 1)
                if self.is_compound_type(var_type.value_type):
                    parsed += ", " + generate_function(var_type.value_type, True, depth + 1)
                else:
                    #ignores the parsed return, only called for the side-effect of changing the returns var to value_type
                    _ = generate_function(var_type.value_type, True, depth + 1)
            elif name == "UInt":
                self.__used_primitive_types.add(self.__sol_to_py_lookup[name + str(var_type.bits_count)])
                returns =  self.__sol_to_py_lookup[name + str(var_type.bits_count)]
            elif name == "FixedBytes":
                self.__used_primitive_types.add(self.__sol_to_py_lookup[name + str(var_type.bytes_count)])
                returns =  self.__sol_to_py_lookup[name + str(var_type.bytes_count)]
            else:
                if use_parse:
                    parsed += self.__sol_to_py_lookup[name]
                else:
                    parsed += ""
                returns = self.__sol_to_py_lookup[name]

            return parsed

        getter_params =  "self, " + generate_function(decl.type, False, 0)
        getter_params += ", params: Optional[TxParams] = None" if len(getter_params) > len("self, ") else "params: Optional[TxParams] = None"
        self.add_str_to_contract_types(1, "def " + decl.name + '(' + getter_params + ") -> " + (returns if returns else "None") + ':', 1)
        if param_names:
            param_names = param_names[:-2]
        #self.add_str_to_contract_types(2, "pass" + " " + param_names, 2) 
        #print(decl.function_selector[3:].decode("utf-8"))
        self.add_str_to_contract_types(2, "return self.transact(\"" + decl.function_selector.hex() + '\", [' + param_names + ']' + ", params)", 2)
        #print(self.__contract_types)


    def generate_types_contract(self, contract: ContractDefinition, generate_template: bool) -> None:
        #bool indicating whether the given contract should inherit from Contract class
        inhertits_contract: bool = True
        base_names: str = ""
        base_imports: str = ""

        #TODO needed to inherit from the base contracts
        for base in contract.base_contracts:
            parent_contract: ContractDefinition = base.base_name.referenced_declaration
            if parent_contract.parent.source_unit_name == contract.parent.source_unit_name:
                if parent_contract.kind == ContractKind.CONTRACT and not parent_contract.abstract:
                    inhertits_contract = False
                    #TODO can be in different src unit?
                    #TODO might be needed to store in a different path
                    self.generate_types_contract(parent_contract, True)
                elif parent_contract.kind == ContractKind.INTERFACE and parent_contract.structs:
                    #TODO will nevever inherit from Contract, will probably not need template (aka imports)
                    #will only be generated to contain the user defined types
                    self.generate_types_interface(parent_contract, False)
                elif parent_contract.kind == ContractKind.CONTRACT and parent_contract.abstract and parent_contract.structs:
                    self.generate_types_undeployable_contract(parent_contract, False)
            else:
                base_names += parent_contract.name + ", "
                base_imports += self.generate_import(parent_contract.name, parent_contract.parent.source_unit_name)
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
        self.generate_contract_template(contract, base_names, base_imports)

        if contract.enums:
            self.generate_types_enum(contract)

        if contract.structs:
            self.generate_types_struct(contract.structs)

        if contract.kind == ContractKind.CONTRACT and not contract.abstract or contract.kind == ContractKind.LIBRARY:
            for var in contract.declared_variables:
                if var.visibility == Visibility.EXTERNAL or var.visibility == Visibility.PUBLIC:
                    self.generate_func_from_instance_var(var)
            for fn in contract.functions:
                if fn.function_selector:
                    params_names, params = self.generate_func_params(fn)
                    self.add_str_to_contract_types(1, f"def {fn.name}(self{params}) -> {self.generate_func_returns(fn)}:", 1)
                    self.add_str_to_contract_types(2, f"return self.transact(\"{fn.function_selector.hex()}\", [{params_names}], params)", 3)

            for variable in contract.declared_variables:
                if isinstance(variable.type_name, Mapping):
                    variable.type


    def generate_types_source_unit(self, unit: SourceUnit) -> None:
        for contract in unit.contracts:
            if contract.kind == ContractKind.CONTRACT and not contract.abstract:
                self.generate_types_contract(contract, True)
            elif contract.kind == ContractKind.LIBRARY:
                continue
        self.generate_primitive_imports()


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
                f.write(self.__source_unit_imports + self.__source_unit_types)
        else:
            unit_path.touch()
            unit_path.write_text(self.__source_unit_imports + self.__source_unit_types)


    #clean the instance variables to enable generating a new source unit
    def cleanup_source_unit(self):
        self.__source_unit_types = ""
        self.__used_primitive_types = set()
        self.__source_unit_imports = ""
        self.__default_imports_generated = False


    def generate_types(self, overwrite: bool = False) -> None:
        #compile proj and generate ir
        #TODO fail if any compile erors
        self.run_compile() 
        self.clean_type_dir()
        for _, unit in self.__source_units.items():
            self.generate_types_source_unit(unit)
            self.write_source_unit_to_file(unit.source_unit_name)
            self.cleanup_source_unit()
