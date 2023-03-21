from pathlib import Path
from typing import Callable, Iterable, List, Tuple

import rich_click as click


def _get_module_name(path: Path, root: Path) -> str:
    path = path.with_suffix("")
    return ".".join(path.relative_to(root).parts)


@click.command(name="run")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--debug", "-d", is_flag=True, default=False, help="Attach debugger on exception."
)
def run_run(paths: Tuple[str, ...], debug: bool) -> None:
    """Run a Woke script."""

    import importlib.util
    import inspect
    import sys

    from woke.config import WokeConfig
    from woke.development.globals import (
        attach_debugger,
        reset_exception_handled,
        set_exception_handler,
    )

    from .console import console

    config = WokeConfig()
    config.load_configs()

    if len(paths) == 0:
        paths = (str(config.project_root_path / "scripts"),)

    py_files = set()

    for path in paths:
        script_path = Path(path).resolve()

        if script_path.is_file() and script_path.match("*.py"):
            py_files.add(script_path)
        elif script_path.is_dir():
            for p in script_path.rglob("*.py"):
                if p.is_file():
                    py_files.add(p)
        else:
            raise ValueError(f"'{script_path}' is not a Python file or directory.")

    run_functions: List[Callable] = []

    sys.path.insert(0, str(config.project_root_path))
    for file in sorted(py_files):
        module_name = _get_module_name(file, config.project_root_path)
        module_spec = importlib.util.spec_from_file_location(module_name, file)
        if module_spec is None or module_spec.loader is None:
            raise ValueError()
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)

        functions: Iterable[Callable] = (
            func
            for _, func in inspect.getmembers(module, inspect.isfunction)
            if func.__module__ == module_name and func.__name__ == "main"
        )
        run_functions.extend(functions)

    if debug:
        set_exception_handler(attach_debugger)

    if len(run_functions) == 0:
        console.print("[yellow]No 'main' functions found in scripts.[/]")
        return

    for func in run_functions:
        console.print(f"Running {func.__module__}...")
        try:
            func()
        finally:
            if debug:
                reset_exception_handled()
