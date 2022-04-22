from typing import Tuple, AnyStr, List, Set
from pathlib import Path
import asyncio

import click
from click.core import Context
from rich.panel import Panel

from woke.a_config import WokeConfig
from woke.d_compile import SolidityCompiler, SolcOutput
from woke.d_compile.solc_frontend.input_data_model import SolcOutputSelectionEnum
from woke.e_ast_parsing.b_solc.c_ast_nodes import AstSolc
from .console import console


@click.command(name="compile")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--parse", is_flag=True, default=False, help="Also try to parse the generated AST."
)
@click.option(
    "--no-artifacts", is_flag=True, default=False, help="Do not write build artifacts."
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force recompile the project without previous build artifacts.",
)
@click.pass_context
def run_compile(
    ctx: Context, files: Tuple[str], parse: bool, no_artifacts: bool, force: bool
) -> None:
    """Compile the project."""
    config = WokeConfig(woke_root_path=ctx.obj["woke_root_path"])
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    sol_files: List[Path] = []
    if len(files) == 0:
        contracts_path = config.project_root_path / "contracts"
        sol_files = [path for path in contracts_path.rglob("*.sol") if path.is_file()]

        if len(sol_files) == 0:
            pass
    else:
        for file in files:
            path = Path(file)
            if not path.is_file() or not path.match("*.sol"):
                raise ValueError(f"Argument `{file}` is not a Solidity file.")
            sol_files.append(path)

    compiler = SolidityCompiler(config, sol_files)
    # TODO Allow choosing build artifacts subset in compile subcommand
    outputs: List[SolcOutput] = asyncio.run(
        compiler.compile(
            [SolcOutputSelectionEnum.ALL],  # type: ignore
            write_artifacts=(not no_artifacts),
            reuse_latest_artifacts=(not force),
        )
    )

    for output in outputs:
        for error in output.errors:
            if error.formatted_message is not None:
                console.print(Panel(error.formatted_message, highlight=True))
            else:
                console.print(Panel(error.message, highlight=True))

    if parse:
        for output in outputs:
            for source_unit_name, info in output.sources.items():
                AstSolc.parse_obj(info.ast)
