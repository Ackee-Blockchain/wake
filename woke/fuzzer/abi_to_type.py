import asyncio
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


def run_compile(config: WokeConfig) -> Dict[Path, SourceUnit]:
    """Compile the project."""
    sol_files: Set[Path] = set()
    for file in config.project_root_path.rglob("**/*.sol"):
        if (
            not any(is_relative_to(file, p) for p in config.compiler.solc.ignore_paths)
            and file.is_file()
        ):
            sol_files.add(file)

    compiler = SolidityCompiler(config)
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
    source_units: Dict[Path, SourceUnit] = {}

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
            source_units[path] = SourceUnit(init, ast)

    reference_resolver.run_post_process_callbacks(
        CallbackParams(source_units=source_units)
    )

    return source_units


def generate_types_contract(contract: ContractDefinition):
    for variable in contract.declared_variables:
        print("variable value: ", variable)
        if isinstance(variable.type_name, Mapping):
            variable.type


def generate_types_source_unit(unit: SourceUnit) -> None:
    for contract in unit.contracts:
        if contract.kind == ContractKind.CONTRACT and not contract.abstract:
            generate_types_contract(contract)
        elif contract.kind == ContractKind.LIBRARY:
            continue


def generate_types(config: WokeConfig, overwrite: bool = False) -> None:
    # compile proj and generate ir
    source_units: Dict[Path, SourceUnit] = run_compile(config)
    types: str = ""
    for path, unit in source_units.items():
        generate_types_source_unit(unit)
