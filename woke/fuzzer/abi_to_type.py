import asyncio
from distutils.command.clean import clean
from pathlib import Path, PurePath
import shutil
import string
from pathlib import Path, PurePath
from typing import Dict, List, Mapping, Set, Tuple

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
from ..ast.ir.meta.source_unit import SourceUnit
from ..ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from ..ast.ir.utils import IrInitTuple
from ..cli.console import console
from ..compile.compilation_unit import CompilationUnit
from ..compile.solc_frontend import SolcOutputErrorSeverityEnum
from ..utils.file_utils import is_relative_to


#tab space width for indentation
TAB_WIDTH = 4

class TypeGenerator():
    __config: WokeConfig
    __indentation: int
    #generated types for the given source unit
    __unit_types: str
    __source_units: Dict[Path, SourceUnit]
    __pytypes_dir: Path


    def __init__(
        self, config: WokeConfig):
        self.__config = config
        self.__indentation = 0
        self.__unit_types = ""
        self.__source_units = {}
        self.__pytypes_dir = config.project_root_path / "pytypes"


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
        unit_path = self.__pytypes_dir / unit_name
        if any(unit_path.iterdir()):
            raise ValueError(f"'{unit_name}' directory is not empty.")
        unit_path.write_text(self.__unit_types)


    def add_str_to_unit_types(self, string: str): 
        self.__unit_types += self.__indentation * ' ' + str


    def generate_contract_template(self, contract: ContractDefinition):
        self.add_str_to_unit_types("class " + contract.name + "(Contract:)")
        self.__indentation = 1 * TAB_WIDTH
        #TODO add abi
        self.add_str_to_unit_types("abi = json.loads(TODO)")
        #TODO add bytecode
        self.add_str_to_unit_types("bytecode = TODO")
        self.add_str_to_unit_types('\n')


    def generate_types_contract(self, contract: ContractDefinition) -> string:
        self.__indentation = 1 * TAB_WIDTH
        self.generate_contract_template(contract)

        for fn in contract.functions:
            pass

        for variable in contract.declared_variables:
            print("variable value: ", variable)
            if isinstance(variable.type_name, Mapping):
                variable.type


    def generate_types_source_unit(self, unit: SourceUnit) -> None:
        for contract in unit.contracts:
            if contract.kind == ContractKind.CONTRACT and not contract.abstract:
                self.generate_types_contract(contract)
            elif contract.kind == ContractKind.LIBRARY:
                continue
        self.write_unit_types_to_file(unit.source_unit_name)


    def clean_type_dir(self):
        """
        instead of recursive removal of type files inside pytypes dir
        remove the root and recreate it
        """
        if self.__pytypes_dir.exists:
            shutil.rmtree(self.__pytypes_dir)
        self.__pytypes_dir.mkdir(exist_ok=True)


    def generate_types(self, overwrite: bool = False) -> None:
        #compile proj and generate ir
        #TODO fail if any compile erors
        self.run_compile() 
        self.clean_type_dir()
        for path, unit in self.__source_units.items():
            self.generate_types_source_unit(unit)
