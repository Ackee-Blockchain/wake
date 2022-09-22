import asyncio
from pathlib import Path, PurePath
from typing import Dict, List, Set, Tuple

import click
import rich.terminal_theme
from intervaltree import IntervalTree
from rich.panel import Panel

from ..analysis.detectors.api import detect, print_detection, print_detectors
from ..ast.ir.meta.source_unit import SourceUnit
from ..ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from ..ast.ir.utils import IrInitTuple
from ..ast.nodes import AstSolc
from ..compile import SolcOutput, SolcOutputSelectionEnum, SolidityCompiler
from ..compile.compilation_unit import CompilationUnit
from ..compile.solc_frontend import SolcOutputErrorSeverityEnum
from ..config import WokeConfig
from ..utils.file_utils import is_relative_to
from .console import console


@click.command(name="detect")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--svg", is_flag=True, default=False, help="Capture the output as an SVG file."
)
@click.pass_context
def run_detect(ctx: click.Context, paths: Tuple[str], svg: bool) -> None:
    """Run vulnerability detectors on the project."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    sol_files: Set[Path] = set()
    if len(paths) == 0:
        for file in config.project_root_path.rglob("**/*.sol"):
            if (
                not any(
                    is_relative_to(file, p) for p in config.compiler.solc.ignore_paths
                )
                and file.is_file()
            ):
                sol_files.add(file)
    else:
        for p in paths:
            path = Path(p)
            if path.is_file():
                if not path.match("*.sol"):
                    raise ValueError(f"Argument `{p}` is not a Solidity file.")
                sol_files.add(path)
            elif path.is_dir():
                for file in path.rglob("**/*.sol"):
                    if (
                        not any(
                            is_relative_to(file, p)
                            for p in config.compiler.solc.ignore_paths
                        )
                        and file.is_file()
                    ):
                        sol_files.add(file)
            else:
                raise ValueError(f"Argument `{p}` is not a file or directory.")

    compiler = SolidityCompiler(config)
    outputs: List[Tuple[CompilationUnit, SolcOutput]] = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.AST],
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
        return

    processed_files: Set[Path] = set()
    reference_resolver = ReferenceResolver()
    interval_trees: Dict[Path, IntervalTree] = {}
    source_units: Dict[Path, SourceUnit] = {}

    for cu, output in outputs:
        for source_unit_name, info in output.sources.items():
            path = cu.source_unit_name_to_path(PurePath(source_unit_name))
            ast = AstSolc.parse_obj(info.ast)

            reference_resolver.index_nodes(ast, path, cu.hash)

            if path in processed_files:
                continue
            processed_files.add(path)
            interval_trees[path] = IntervalTree()

            init = IrInitTuple(
                path,
                path.read_bytes(),
                cu,
                interval_trees[path],
                reference_resolver,
            )
            source_units[path] = SourceUnit(init, ast)

    reference_resolver.run_post_process_callbacks(
        CallbackParams(interval_trees=interval_trees, source_units=source_units)
    )

    if svg:
        print_detectors(theme="vs")
    else:
        print_detectors()

    for detection in detect(source_units):
        if svg:
            print_detection(detection, theme="vs")
        else:
            print_detection(detection)

    if svg:
        console.save_svg(
            "woke-detections.svg",
            title="Woke",
            theme=rich.terminal_theme.DEFAULT_TERMINAL_THEME,
        )
