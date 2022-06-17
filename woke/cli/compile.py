import asyncio
from pathlib import Path
from typing import AnyStr, List, Set, Tuple

import click
from click.core import Context
from rich.panel import Panel

from woke.ast.nodes import AstSolc
from woke.compile import SolcOutput, SolidityCompiler
from woke.compile.solc_frontend.input_data_model import SolcOutputSelectionEnum
from woke.config import WokeConfig

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

    compiler = SolidityCompiler(config)
    # TODO Allow choosing build artifacts subset in compile subcommand
    outputs = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=(not no_artifacts),
            reuse_latest_artifacts=(not force),
            maximize_compilation_units=True,
        )
    )

    for _, output in outputs:
        for error in output.errors:
            if error.formatted_message is not None:
                console.print(Panel(error.formatted_message, highlight=True))
            else:
                console.print(Panel(error.message, highlight=True))

    if parse:
        for _, output in outputs:
            for source_unit_name, info in output.sources.items():
                AstSolc.parse_obj(info.ast)
