from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

import rich_click as click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

if TYPE_CHECKING:
    from wake.config import WakeConfig
    from wake.mutators.api import Mutation, Mutator


class TestResult(Enum):
    """Result of running tests on a mutation."""
    PASSED = auto()
    FAILED = auto()
    COMPILE_ERROR = auto()
    TIMEOUT = auto()


def split_csv(ctx, param, value) -> List[str]:
    """Callback to split space/comma-separated values and flatten."""
    if not value:
        return []
    result = []
    for item in value:
        # Split on both comma and space
        for v in item.replace(",", " ").split():
            v = v.strip()
            if v:
                result.append(v)
    return result


def split_csv_paths(ctx, param, value) -> List[Path]:
    """Callback to split space/comma-separated paths and flatten."""
    if not value:
        return []
    result = []
    for item in value:
        # Split on both comma and space
        for v in item.replace(",", " ").split():
            v = v.strip()
            if v:
                p = Path(v)
                if not p.exists():
                    raise click.BadParameter(f"Path does not exist: {v}")
                result.append(p)
    return result


def discover_mutators() -> dict[str, type["Mutator"]]:
    """Discover all mutator classes from wake_mutators package."""
    import importlib
    import pkgutil
    
    import wake_mutators as mutators_pkg
    from wake.mutators.api import Mutator
    
    found = {}
    
    for importer, modname, ispkg in pkgutil.iter_modules(mutators_pkg.__path__):
        if modname.startswith("_"):
            continue
        
        module = importlib.import_module(f"wake_mutators.{modname}")
        
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, Mutator)
                and attr is not Mutator
                and attr.__module__ == module.__name__
            ):
                found[attr.name] = attr
    
    return found


async def compile_project(config: "WakeConfig", contract_paths: List[Path]):
    """Compile the project and return the build."""
    from wake.compiler.compiler import SolidityCompiler
    from wake.compiler.solc_frontend import SolcOutputSelectionEnum
    
    compiler = SolidityCompiler(config)
    compiler.load()
    
    build, errors = await compiler.compile(
        contract_paths,
        [SolcOutputSelectionEnum.AST],
        write_artifacts=False,
    )
    
    return build


def collect_mutations(
    config: "WakeConfig",
    contract_paths: List[Path],
    mutator_classes: List[type["Mutator"]],
    console: Console,
) -> List["Mutation"]:
    """Run mutators on contracts to collect all mutations."""
    from wake.core.visitor import visit_map, group_map
    
    start = time.perf_counter()
    with console.status("[bold green]Compiling contracts...[/]"):
        build = asyncio.run(compile_project(config, contract_paths))
    end = time.perf_counter()
    console.log(f"[green]Compiled in [bold green]{end - start:.2f} s[/bold green][/]")
    
    all_mutations = []
    
    start = time.perf_counter()
    with console.status("[bold green]Collecting mutations...[/]"):
        for mutator_cls in mutator_classes:
            mutator = mutator_cls()
            
            for path in contract_paths:
                source_unit = build.source_units.get(path)
                if source_unit is None:
                    continue
                
                mutator._current_file = path
                
                for node in source_unit:
                    if node.ast_node.node_type in group_map:
                        for group in group_map[node.ast_node.node_type]:
                            if group in visit_map:
                                visit_map[group](mutator, node)
                    
                    if node.ast_node.node_type in visit_map:
                        visit_map[node.ast_node.node_type](mutator, node)
            
            all_mutations.extend(mutator.mutations)
    
    end = time.perf_counter()
    console.log(f"[green]Found [bold green]{len(all_mutations)}[/bold green] mutation(s) in [bold green]{end - start:.2f} s[/bold green][/]")
    
    return all_mutations


def run_tests(test_paths: List[str], timeout: int = 120) -> TestResult:
    """Regenerate pytypes and run wake test. Return TestResult."""
    try:
        compile_result = subprocess.run(
            ["wake", "up", "pytypes"],
            capture_output=True,
            timeout=timeout,
            cwd=Path.cwd(),
        )
        
        if compile_result.returncode != 0:
            return TestResult.COMPILE_ERROR
    except subprocess.TimeoutExpired:
        return TestResult.TIMEOUT
    
    cmd = ["wake", "test", "-x"] + test_paths
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            cwd=Path.cwd(),
        )
        return TestResult.PASSED if result.returncode == 0 else TestResult.FAILED
    except subprocess.TimeoutExpired:
        return TestResult.TIMEOUT


@click.command(name="mutate")
@click.option(
    "--contracts",
    "-c",
    multiple=True,
    type=str,
    callback=split_csv_paths,
    help="Contract files to mutate (space or comma-separated).",
)
@click.option(
    "--mutations",
    "-m",
    multiple=True,
    type=str,
    callback=split_csv,
    help="Mutation operators to use (space or comma-separated). Default: all.",
)
@click.option(
    "--list-mutations",
    is_flag=True,
    default=False,
    help="List available mutation operators.",
)
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=60,
    help="Timeout for each test run in seconds.",
)
@click.option(
    "-v",
    "--verbosity",
    default=0,
    count=True,
    help="Increase verbosity.",
)
@click.argument("test_paths", nargs=-1, type=click.Path(exists=True))
@click.pass_context
def run_mutate(
    context: click.Context,
    contracts: List[Path],
    mutations: List[str],
    list_mutations: bool,
    timeout: int,
    verbosity: int,
    test_paths: Tuple[str, ...],
) -> None:
    """ Run mutation testing on Solidity contracts. """
    from wake.config import WakeConfig
    from wake.mutators.api import MutantStatus
    
    console = Console()
    
    # Discover available mutators
    available_mutators = discover_mutators()
    
    if list_mutations:
        table = Table(title="Available Mutation Operators")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        
        for name, cls in sorted(available_mutators.items()):
            table.add_row(name, cls.description)
        
        console.print(table)
        return
    
    # Now contracts is required (but not for --list-mutations)
    if not contracts:
        raise click.BadParameter("--contracts/-c is required when running mutation tests.")
    
    # Default to all tests if none specified
    if test_paths:
        test_paths_list = list(test_paths)
    else:
        tests_dir = Path.cwd() / "tests"
        if tests_dir.exists():
            test_paths_list = [str(p) for p in tests_dir.glob("test_*.py")]
        else:
            test_paths_list = []
        
        if not test_paths_list:
            raise click.BadParameter("No test files found. Specify test paths or create tests/test_*.py files.")
        
        console.log(f"[green]Auto-discovered [bold green]{len(test_paths_list)}[/bold green] test file(s)[/]")
    
    # Select mutators
    if mutations:
        selected = []
        for m in mutations:
            if m not in available_mutators:
                raise click.BadParameter(f"Unknown mutation operator: {m}")
            selected.append(available_mutators[m])
    else:
        selected = list(available_mutators.values())
    
    # Load config
    config = WakeConfig(local_config_path=context.obj.get("local_config_path", None))
    config.load_configs()
    
    # Resolve contract paths
    resolved_contracts = [p.resolve() for p in contracts]
    
    # Print configuration
    console.print()
    console.rule("[bold]Mutation Testing Configuration[/bold]")
    console.print(f"  [dim]Contracts:[/dim]  {', '.join(str(c.name) for c in contracts)}")
    console.print(f"  [dim]Mutations:[/dim]  {', '.join(m.name for m in selected)}")
    console.print(f"  [dim]Tests:[/dim]      {', '.join(test_paths_list)}")
    console.print(f"  [dim]Timeout:[/dim]    {timeout}s")
    console.print()
    
    # Collect all mutations
    all_mutations = collect_mutations(config, resolved_contracts, selected, console)
    
    if not all_mutations:
        console.print("[yellow]No mutations found.[/yellow]")
        return
    
    # Run baseline test first
    console.print()
    with console.status("[bold green]Running baseline tests...[/]"):
        start = time.perf_counter()
        baseline_result = run_tests(test_paths_list, timeout)
        end = time.perf_counter()
    
    if baseline_result != TestResult.PASSED:
        console.log(f"[bold red]Baseline tests failed![/bold red] Fix tests before mutation testing.")
        sys.exit(1)
    
    console.log(f"[green]Baseline tests passed in [bold green]{end - start:.2f} s[/bold green][/]")
    console.print()
    
    # Test each mutation
    results = []
    
    console.rule("[bold]Running Mutations[/bold]")
    console.print()
    
    total_start = time.perf_counter()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Testing mutations...", total=len(all_mutations))
        
        for i, mutation in enumerate(all_mutations, 1):
            progress.update(task, description=f"[cyan]Testing mutation {i}/{len(all_mutations)}")
            
            original_source = mutation.file_path.read_bytes()
            
            try:
                mutated_source = mutation.apply(original_source)
                mutation.file_path.write_bytes(mutated_source)
                
                test_result = run_tests(test_paths_list, timeout)
                
                if test_result == TestResult.PASSED:
                    status = MutantStatus.SURVIVED
                elif test_result == TestResult.FAILED:
                    status = MutantStatus.KILLED
                elif test_result == TestResult.COMPILE_ERROR:
                    status = MutantStatus.COMPILE_ERROR
                elif test_result == TestResult.TIMEOUT:
                    status = MutantStatus.TIMEOUT
                
                results.append((mutation, status))
                
            except Exception as e:
                results.append((mutation, MutantStatus.COMPILE_ERROR))
            
            finally:
                mutation.file_path.write_bytes(original_source)
            
            progress.advance(task)
    
    total_end = time.perf_counter()
    
    # Print detailed results
    if verbosity > 0:
        console.print()
        results_table = Table(title="Mutation Results", show_lines=True)
        results_table.add_column("#", style="dim", width=4)
        results_table.add_column("File", style="cyan")
        results_table.add_column("Line", style="dim", width=6)
        results_table.add_column("Mutation", style="white")
        results_table.add_column("Status", justify="center")
        
        for i, (mutation, status) in enumerate(results, 1):
            if status == MutantStatus.KILLED:
                status_str = "[green]KILLED ✓[/green]"
            elif status == MutantStatus.SURVIVED:
                status_str = "[red]SURVIVED ✗[/red]"
            elif status == MutantStatus.COMPILE_ERROR:
                status_str = "[yellow]COMPILE ERROR ⚠[/yellow]"
            elif status == MutantStatus.TIMEOUT:
                status_str = "[yellow]TIMEOUT ⏱[/yellow]"
            
            results_table.add_row(
                str(i),
                mutation.file_path.name,
                str(mutation.line_number),
                mutation.description,
                status_str,
            )
        
        console.print(results_table)
    
    # Summary
    killed = sum(1 for _, s in results if s == MutantStatus.KILLED)
    survived = sum(1 for _, s in results if s == MutantStatus.SURVIVED)
    compile_errors = sum(1 for _, s in results if s == MutantStatus.COMPILE_ERROR)
    timeouts = sum(1 for _, s in results if s == MutantStatus.TIMEOUT)
    
    console.print()
    console.rule("[bold]Mutation Testing Summary[/bold]")
    console.print()
    
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Label", style="dim")
    summary_table.add_column("Value", justify="right")
    
    summary_table.add_row("Total mutations", str(len(results)))
    summary_table.add_row("Killed", f"[green]{killed}[/green]")
    summary_table.add_row("Survived", f"[red]{survived}[/red]")
    if compile_errors:
        summary_table.add_row("Compile Errors", f"[yellow]{compile_errors}[/yellow]")
    if timeouts:
        summary_table.add_row("Timeouts", f"[yellow]{timeouts}[/yellow]")
    summary_table.add_row("Time elapsed", f"{total_end - total_start:.2f} s")
    
    console.print(summary_table)
    
    if killed + survived > 0:
        score = killed / (killed + survived) * 100
        console.print()
        if score >= 80:
            console.print(f"[bold green]Mutation Score: {score:.1f}%[/bold green]")
        elif score >= 50:
            console.print(f"[bold yellow]Mutation Score: {score:.1f}%[/bold yellow]")
        else:
            console.print(f"[bold red]Mutation Score: {score:.1f}%[/bold red]")
    
    # List survivors
    survivors = [(m, s) for m, s in results if s == MutantStatus.SURVIVED]
    if survivors:
        console.print()
        console.rule("[bold red]Surviving Mutations[/bold red]")
        console.print()
        console.print("[dim]These mutations were not caught by tests - consider improving test coverage:[/dim]")
        console.print()
        
        survivor_table = Table(show_header=True, box=None)
        survivor_table.add_column("File", style="cyan")
        survivor_table.add_column("Line", style="dim")
        survivor_table.add_column("Mutation")
        
        for mutation, _ in survivors:
            survivor_table.add_row(
                mutation.file_path.name,
                str(mutation.line_number),
                mutation.description,
            )
        
        console.print(survivor_table)
    
    # Final status
    console.print()
    if survived == 0:
        console.print("[bold green]All mutations were killed! ✓[/bold green]")
    else:
        console.print(f"[bold red]{survived} mutation(s) survived - tests need improvement[/bold red]")
    
    sys.exit(0 if survived == 0 else 1)