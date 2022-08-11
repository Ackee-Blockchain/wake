from abc import ABC
from ast import parse
import asyncio
from distutils.command.clean import clean
from genericpath import exists
from pathlib import Path, PurePath
from re import A
import shutil
import string
from pathlib import Path, PurePath
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
from ..ast.ir.declaration.function_definition import FunctionDefinition
from ..compile.compilation_unit import CompilationUnit
from ..compile.solc_frontend import SolcOutputErrorSeverityEnum
from ..utils.file_utils import is_relative_to


class A:
    pass

class B:
    pass

class C:
    pass

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
    __unit_types: str
    __source_units: Dict[Path, SourceUnit]
    __pytypes_dir: Path
    __sol_to_py_lookup: Dict[type, str]


    def __init__(
        self, config: WokeConfig):
        self.__config = config
        self.__unit_types = ""
        self.__source_units = {}
        self.__pytypes_dir = config.project_root_path / "pytypes"
        self.__sol_to_py_lookup = {}
        self.__init_sol_to_py_types()


    def __init_sol_to_py_types(self):
        self.__sol_to_py_lookup[expr_types.Address.__name__] = "AnyAddress"
        self.__sol_to_py_lookup[expr_types.String.__name__] = "str"
        self.__sol_to_py_lookup[expr_types.Array.__name__] = "arr"
        self.__sol_to_py_lookup[expr_types.Struct.__name__] = "struct"
        self.__sol_to_py_lookup[expr_types.UInt.__name__] = "uint"
        self.__sol_to_py_lookup[expr_types.Bool.__name__] = "bool"


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


    def write_unit_types_to_file(self, unit_name: str):
        self.__pytypes_dir.mkdir(exist_ok=True)
        unit_path = (self.__pytypes_dir / unit_name).with_suffix(".py")
        unit_path_parent = unit_path.parent
        #TODO validate whether project root can become paraent
        unit_path_parent.mkdir(parents=True,exist_ok=True)
        unit_path.touch()
        unit_path.write_text(self.__unit_types)


    def add_str_to_unit_types(self, num_of_indentation: int, string: str, num_of_newlines: int): 
        self.__unit_types += num_of_indentation * TAB_WIDTH * ' ' + string + num_of_newlines * '\n'

    #TODO add generating python imports
    def generate_imports(self):
        pass

    def generate_contract_template(self, contract: ContractDefinition, base_names: str):
        self.add_str_to_unit_types(0, DEFAULT_IMPORTS, 2)
        self.add_str_to_unit_types(0, "class " + contract.name + "(" + base_names + "):", 1)
        #TODO add abi
        self.add_str_to_unit_types(1, "abi = json.loads(TODO)", 1)
        #TODO add bytecode
        self.add_str_to_unit_types(1, "bytecode = TODO", 1)
        self.add_str_to_unit_types(0, "", 1)


    def generate_types_enum(self, contract: ContractDefinition) -> None:
        enums = contract.enums

    def generate_types_struct(self, structs: List[StructDefinition]) -> None:
        print("number of structs is: ", len(structs))
        for struct in structs:
            self.add_str_to_unit_types(1, "@dataclass", 1)
            self.add_str_to_unit_types(1, f"class {struct.name}:", 1)
            for member in struct.members:
                self.add_str_to_unit_types(2, member.canonical_name.split('.')[-1] + ": " + self.parse_var_declaration(member), 1)
            self.add_str_to_unit_types(0, "", 2)


    def parse_var_declaration(self, decl: VariableDeclaration) -> str:
        name = decl.type.__class__.__name__
        parsed: str = ""
        if name == "Struct":
            parsed += decl.type.name
        elif name == "Array":
            #TODO implement nested arrays
            parsed = "List[" + decl.type.base_type.__class__.__name__ + "]"
        else:
            parsed = self.__sol_to_py_lookup[name]
        return parsed


    def generate_func_params(self, fn: FunctionDefinition) -> Tuple[str, str]:
        params: str = ""
        #params_names are later inserted as an argument to the self.transact call
        params_names: str = ""
        for par in fn.parameters.parameters:
            params_names += par.name + ", "
            params += ", " + par.name + ": " + self.parse_var_declaration(par)
        params += ", params: Optional[TxParams] = None"
        if params_names:
            return params_names[:-2], params
        return params_names, params


    def generate_func_returns(self, fn: FunctionDefinition) -> str:
        return_params: str = ""
        for ret in fn.return_parameters.parameters:
            return_params += self.parse_var_declaration(ret) + ", "
        if return_params:
            return return_params[:-2]
        else:
            return return_params + "None"


    def generate_types_interface(self, interface: ContractDefinition, generate_template: bool) -> None:
        pass

    def generate_types_abstract_contract(self, abstract_contract: ContractDefinition, generate_template: bool) -> None:
        pass

    def generate_types_contract(self, contract: ContractDefinition, generate_template: bool) -> None:
        inhertits_contract: bool = True
        base_names: str = ""

        #TODO needed to inherit from the base contracts
        for base in contract.base_contracts:
            parent_contract = base.base_name.referenced_declaration
            if parent_contract.kind == ContractKind.CONTRACT and not parent_contract.abstract:
                inhertits_contract = False
                #TODO can be in different src unit?
                #TODO might be needed to store in a different path
                self.generate_types_contract(parent_contract, True)
            elif parent_contract.kind == ContractKind.INTERFACE and parent_contract.structs:
                #TODO will nevever inherit from Contract, will probably not need template (aka imports)
                #will only be generated to contain the user defined types
                self.generate_types_interface(parent_contract, False)
            elif parent_contract.kind == ContractKind.CONTRACT and parent_contract.abstract:
                self.generate_types_abstract_contract(parent_contract, False)

            #print("source unit: ", base.base_name.referenced_declaration.parent.source_unit_name)
            #print("source unit: ", base.base_name.referenced_declaration.kind)
            #print("source unit: ", base.base_parent.source_unit_name)
            #print("is abstract: ", base.base_parent.referenced_declaration.abstract)
            #print("kind: ", base.parent.kind)

        if generate_template:
            print("inside generate template")
            if inhertits_contract:
                base_names = "Contract, " + base_names if base_names else "Contract"

            self.generate_contract_template(contract, base_names)

        if contract.enums:
            self.generate_types_enum(contract)

        if contract.structs:
            self.generate_types_struct(contract.structs)

        if contract.kind == ContractKind.CONTRACT and not contract.abstract or contract.kind == ContractKind.LIBRARY:
            for fn in contract.functions:
                if fn.function_selector:
                    params_names, params = self.generate_func_params(fn)
                    self.add_str_to_unit_types(1, f"def {fn.name}(self{params}) -> {self.generate_func_returns(fn)}:", 1)
                    self.add_str_to_unit_types(2, f"return self.transact(\"{fn.function_selector}\", [{params_names}], params)", 3)

            for variable in contract.declared_variables:
                if isinstance(variable.type_name, Mapping):
                    variable.type


    def generate_types_source_unit(self, unit: SourceUnit) -> None:
        for contract in unit.contracts:
            if contract.kind == ContractKind.CONTRACT and not contract.abstract:
                self.generate_types_contract(contract, True)
            elif contract.kind == ContractKind.LIBRARY:
                continue
        self.write_unit_types_to_file(unit.source_unit_name)


    def clean_type_dir(self):
        """
        instead of recursive removal of type files inside pytypes dir
        remove the root and recreate it
        """
        if self.__pytypes_dir.exists():
            shutil.rmtree(self.__pytypes_dir)
        self.__pytypes_dir.mkdir(exist_ok=True)


    def generate_types(self, overwrite: bool = False) -> None:
        #compile proj and generate ir
        #TODO fail if any compile erors
        self.run_compile() 
        self.clean_type_dir()
        for path, unit in self.__source_units.items():
            self.generate_types_source_unit(unit)
