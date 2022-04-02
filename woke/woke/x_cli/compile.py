from typing import Tuple, AnyStr, List, Set
from pathlib import Path
import asyncio

import click
from click.core import Context

from woke.a_config import WokeConfig
from woke.d_compile import SolidityCompiler, SolcOutput
from woke.d_compile.solc_frontend.input_data_model import SolcOutputSelectionEnum
from woke.e_ast_parsing.b_solc.c_ast_nodes import AstSolc


@click.command(name="compile")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--parse", is_flag=True, default=False)
@click.option("--no-artifacts", is_flag=True, default=False)
@click.pass_context
def run_compile(
    ctx: Context, files: Tuple[str], parse: bool, no_artifacts: bool
) -> None:
    config = WokeConfig()
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

    x = SolidityCompiler(config, sol_files)
    # TODO Allow choosing build artifacts subset in compile subcommand
    outputs: List[SolcOutput] = asyncio.run(
        x.compile([SolcOutputSelectionEnum.ALL], write_artifacts=(not no_artifacts))
    )

    if parse:
        for output in outputs:
            for source_unit_name, info in output.sources.items():
                AstSolc.parse_obj(info.ast)
