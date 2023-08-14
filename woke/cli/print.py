import asyncio
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Set, Type, Union

import rich_click as click

if TYPE_CHECKING:
    from woke.printers import Printer


class PrintCli(click.RichGroup):  # pyright: ignore reportPrivateImportUsage
    _plugins_loaded = False
    _plugin_commands: Dict[str, click.Command] = {}

    def __init__(
        self,
        name: Optional[str] = None,
        commands: Optional[
            Union[Dict[str, click.Command], Sequence[click.Command]]
        ] = None,
        **attrs: Any,
    ):
        super().__init__(name=name, commands=commands, **attrs)

        for command in self.commands.values():
            self._inject_params(command)

    @staticmethod
    def _inject_params(command: click.Command) -> None:
        command.params.append(
            click.Argument(
                ["paths"],
                nargs=-1,
                type=click.Path(exists=True),
            )
        )

    def _load_plugins(self) -> None:
        if sys.version_info < (3, 10):
            from importlib_metadata import entry_points
        else:
            from importlib.metadata import entry_points

        printer_entry_points = entry_points().select(group="woke.plugins.printers")
        for entry_point in printer_entry_points:
            entry_point.load()

        if (
            Path.cwd().joinpath("printers").is_dir()
            and Path.cwd().joinpath("printers/__init__.py").is_file()
        ):
            from importlib.util import module_from_spec, spec_from_file_location

            sys.path.insert(0, str(Path.cwd()))
            spec = spec_from_file_location("printers", "printers/__init__.py")
            if spec is not None and spec.loader is not None:
                module = module_from_spec(spec)
                spec.loader.exec_module(module)

        self._plugins_loaded = True

    def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
        self._inject_params(cmd)
        super().add_command(cmd, name)

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        if not self._plugins_loaded:
            self._load_plugins()
        return self.commands.get(cmd_name)

    def list_commands(self, ctx: click.Context) -> List[str]:
        if not self._plugins_loaded:
            self._load_plugins()
        return sorted(self.commands)

    def invoke(self, ctx: click.Context):
        ctx.obj["subcommand_args"] = ctx.args
        ctx.obj["subcommand_protected_args"] = ctx.protected_args
        super().invoke(ctx)


@click.group(
    name="print", cls=PrintCli, context_settings={"auto_envvar_prefix": "WOKE_PRINTER"}
)
@click.option(
    "--no-artifacts", is_flag=True, default=False, help="Do not write build artifacts."
)
@click.pass_context
def run_print(ctx: click.Context, no_artifacts: bool) -> None:
    """Run a printer."""

    if "--help" in ctx.obj["subcommand_args"]:
        return

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild
    from ..compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
    from ..config import WokeConfig
    from ..utils import get_class_that_defined_method
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
                    is_relative_to(file, p) for p in config.compiler.solc.ignore_paths
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

    assert compiler.latest_build_info is not None
    assert compiler.latest_graph is not None

    assert isinstance(ctx.command, PrintCli)
    assert ctx.invoked_subcommand is not None
    command = ctx.command.get_command(ctx, ctx.invoked_subcommand)
    assert command is not None
    assert command.name is not None

    if hasattr(config.printers, command.name):
        default_map = getattr(config.printers, command.name)
    else:
        default_map = None

    cls: Type[Printer] = get_class_that_defined_method(
        command.callback
    )  # pyright: ignore reportGeneralTypeIssues
    if cls is not None:

        def _callback(*args, **kwargs):
            instance.paths = [Path(p).resolve() for p in kwargs.pop("paths", [])]

            original_callback(
                instance, *args, **kwargs
            )  # pyright: ignore reportOptionalCall

        instance = cls()
        instance.build = build
        instance.build_info = compiler.latest_build_info
        instance.config = config
        instance.console = console
        instance.imports_graph = (  # pyright: ignore reportGeneralTypeIssues
            compiler.latest_graph.copy()
        )

        original_callback = command.callback
        command.callback = _callback

        sub_ctx = command.make_context(
            command.name,
            [*ctx.obj["subcommand_protected_args"][1:], *ctx.obj["subcommand_args"]],
            parent=ctx,
            default_map=default_map,
        )
        with sub_ctx:
            sub_ctx.command.invoke(sub_ctx)

        instance._run()
    else:

        def _callback(*args, **kwargs):
            click.get_current_context().obj["paths"] = [
                Path(p).resolve() for p in kwargs.pop("paths", [])
            ]

            original_callback(*args, **kwargs)  # pyright: ignore reportOptionalCall

        args = [*ctx.obj["subcommand_protected_args"][1:], *ctx.obj["subcommand_args"]]
        ctx.obj = {
            "build": build,
            "build_info": compiler.latest_build_info,
            "config": config,
            "console": console,
            "imports_graph": compiler.latest_graph.copy(),
        }

        original_callback = command.callback
        command.callback = _callback

        sub_ctx = command.make_context(
            command.name, args, parent=ctx, default_map=default_map
        )
        with sub_ctx:
            sub_ctx.command.invoke(sub_ctx)

    # avoid double execution of a subcommand
    sys.exit(0)
