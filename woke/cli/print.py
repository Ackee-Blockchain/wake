import asyncio
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, Tuple, DefaultDict, List, Optional

import rich_click as click


@click.group(name="print")
@click.option(
    "--no-artifacts", is_flag=True, default=False, help="Do not write build artifacts."
)
@click.pass_context
def run_print(ctx: click.Context, no_artifacts: bool) -> None:
    """Run a printer."""
    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild
    from ..compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
    from ..config import WokeConfig
    from ..utils.file_utils import is_relative_to
    from .console import console

    config = WokeConfig()
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    sol_files: Set[Path] = set()
    start = time.perf_counter()
    with console.status("[bold green]Searching for *.sol files...[/]"):
        for file in config.project_root_path.rglob("**/*.sol"):
            if (
                not any(
                    is_relative_to(file, p)
                    for p in config.compiler.solc.ignore_paths
                )
                and file.is_file()
            ):
                sol_files.add(file)
    end = time.perf_counter()
    console.log(
        f"[green]Found {len(sol_files)} *.sol files in [bold green]{end - start:.2f} s[/bold green][/]"
    )

    compiler = SolidityCompiler(config)
    compiler.load(console=console)

    build: ProjectBuild
    errors: Set[SolcOutputError]
    build, errors = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=not no_artifacts,
            console=console,
            no_warnings=True,
        )
    )

    errored = any(
        error.severity == SolcOutputErrorSeverityEnum.ERROR for error in errors
    )
    if errored:
        sys.exit(1)

    ctx.obj["config"] = config
    ctx.obj["build"] = build


@run_print.command(name="contracts")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.pass_context
def run_print_contracts(ctx: click.Context, paths: Tuple[str]) -> None:
    from ..compiler.build_data_model import ProjectBuild
    from .console import console
    from woke.utils.file_utils import is_relative_to

    build: ProjectBuild = ctx.obj["build"]

    paths = [Path(p).resolve() for p in paths]

    for path, source_unit in build.source_units.items():
        if len(paths) == 0 or any(is_relative_to(path, p) for p in paths):
            console.print(f"[link=file://{path}]{source_unit.source_unit_name}[/]")
            for contract in source_unit.contracts:
                line, _ = source_unit.get_line_col_from_byte_offset(contract.byte_location[0])
                console.print(f"  [bold][link=file://{path}#{line}]{contract.name}[/][/]")
            console.print()


@run_print.command(name="contract-summary")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--no-immutable", is_flag=True, default=False, help="Do not print immutable variables.")
@click.pass_context
def run_print_summary(ctx: click.Context, paths: Tuple[str], no_immutable: bool) -> None:
    from itertools import chain

    from ..compiler.build_data_model import ProjectBuild
    from .console import console
    from woke.utils.file_utils import is_relative_to

    from woke.ast.enums import StateMutability
    from woke.ast.ir.meta.source_unit import SourceUnit

    from rich.table import Table

    build: ProjectBuild = ctx.obj["build"]

    paths = [Path(p).resolve() for p in paths]

    for path, source_unit in build.source_units.items():
        if len(paths) == 0 or any(is_relative_to(path, p) for p in paths):
            for contract in source_unit.contracts:
                table = Table(title=f"[link=file://{path}]{contract.name}[/]")

                table.add_column("Name")
                table.add_column("Visibility", no_wrap=True)
                table.add_column("Mutability", no_wrap=True)
                table.add_column("Modifiers", no_wrap=True)

                variable_mutability_priority = {
                    "constant": 0,
                    "immutable": 1,
                    "mutable": 2,
                }
                function_mutability_priority = {
                    "pure": 0,
                    "view": 1,
                    "nonpayable": 2,
                    "payable": 3,
                }
                visibility_priority = {
                    "private": 0,
                    "internal": 1,
                    "external": 2,
                    "public": 3,
                }

                variables = []
                functions = []

                for base_contract in contract.linearized_base_contracts:
                    variables.extend(base_contract.declared_variables)
                    for function in base_contract.functions:
                        # TODO constructor, fallback, receive
                        if function.kind == "function" and not any(f.parent in contract.linearized_base_contracts for f in function.child_functions):
                            functions.append(function)

                variables.sort(
                    key=lambda v: (
                        variable_mutability_priority[v.mutability],
                        visibility_priority[v.visibility],
                        v.name,
                    )
                )
                functions.sort(
                    key=lambda f: (
                        function_mutability_priority[f.state_mutability],
                        visibility_priority[f.visibility],
                        f.name,
                    )
                )

                for variable in variables:
                    unit = variable
                    while unit is not None:
                        if isinstance(unit, SourceUnit):
                            break
                        unit = unit.parent
                    assert isinstance(unit, SourceUnit)

                    line, _ = unit.get_line_col_from_byte_offset(variable.byte_location[0])
                    table.add_row(
                        f"[link=vscode://file/{unit.file}:{line}]{variable.name}[/]",
                        variable.visibility,
                        variable.mutability if variable.mutability != "mutable" else "",
                        "",
                    )
                if len(variables) > 0:
                    table.add_row(end_section=True)

                # TODO overriden functions

                for function in functions:
                    unit = function
                    while unit is not None:
                        if isinstance(unit, SourceUnit):
                            break
                        unit = unit.parent
                    assert isinstance(unit, SourceUnit)

                    line, _ = unit.get_line_col_from_byte_offset(function.byte_location[0])
                    table.add_row(
                        f"[link=vscode://file/{unit.file}:{line}]{function.name}[/]",
                        function.visibility,
                        function.state_mutability if function.state_mutability != StateMutability.NONPAYABLE else "",
                        ", ".join(m.modifier_name.referenced_declaration.name for m in function.modifiers),
                    )

                console.print(table)

            console.print()


@dataclass
class NodeInfo:
    locs: int
    path: Optional[Path] = None
    children: DefaultDict[str, "NodeInfo"] = field(default_factory=lambda: defaultdict(lambda: NodeInfo(0)))


@run_print.command(name="assembly-summary")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.pass_context
def run_print_summary(ctx: click.Context, paths: Tuple[str]) -> None:
    from collections import defaultdict

    from ..compiler.build_data_model import ProjectBuild
    from .console import console
    from woke.config import WokeConfig
    from woke.utils.file_utils import is_relative_to
    from woke.ast.ir.statement.inline_assembly import InlineAssembly

    from rich.tree import Tree

    config: WokeConfig = ctx.obj["config"]
    build: ProjectBuild = ctx.obj["build"]

    paths = [Path(p).resolve() for p in paths]

    lines_per_file: DefaultDict[Path, int] = defaultdict(int)

    for path, source_unit in build.source_units.items():
        if len(paths) == 0 or any(is_relative_to(path, p) for p in paths):
            for node in source_unit:
                if isinstance(node, InlineAssembly):
                    start_line, _ = source_unit.get_line_col_from_byte_offset(node.byte_location[0])
                    end_line, _ = source_unit.get_line_col_from_byte_offset(node.byte_location[1])
                    lines_per_file[path] += end_line - start_line

    root = NodeInfo(0)

    for file, lines in lines_per_file.items():
        try:
            rel_path = file.relative_to(config.project_root_path)
        except ValueError:
            rel_path = file

        node = root
        node.locs += lines
        for i, part in enumerate(rel_path.parts):
            node = node.children[part]
            node.locs += lines
            if i == len(rel_path.parts) - 1:
                node.path = file

    tree = Tree(f"{root.locs} LOC")

    def add_node(node: NodeInfo, tree: Tree) -> None:
        for name, child in node.children.items():
            if child.path is None:
                add_node(child, tree.add(f"{name} ({child.locs} LOC)"))
            else:
                add_node(child, tree.add(f"[link=vscode://file/{child.path}]{name}[/] ({child.locs} LOC)"))

    add_node(root, tree)
    console.print(tree)
