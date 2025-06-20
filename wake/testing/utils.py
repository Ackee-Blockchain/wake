from wake.cli.console import console
from wake.development.globals import get_fuzz_test_stats, get_verbosity


def print_fuzzing_stats(terminalreporter):
    verbosity = get_verbosity()

    for name, stats in sorted(get_fuzz_test_stats().items(), key=lambda x: x[0]):
        terminalreporter.write_line(f"Fuzz test '{name}':")

        # Calculate grand total across all flows for this test
        grand_total = sum(sum(rets.values()) for rets in stats.values())
        if grand_total == 0:
            continue

        width = console.width - 6  # Account for padding

        # Find global maximum across all flows and all statuses
        global_max = 0
        for flow_rets in stats.values():
            # Include success count (None key) in max calculation
            if flow_rets:
                global_max = max(global_max, max(flow_rets.values()))

        for flow, rets in sorted(stats.items(), key=lambda x: x[0]):
            terminalreporter.write_line(f"  {flow}:")

            # Get success count but preserve it in rets for next iteration
            success_count = rets.get(None, 0)
            if success_count:
                percentage = success_count / grand_total * 100
                bar_width = int((success_count / global_max) * width)
                terminalreporter.write_line(
                    f"    Success: {success_count} ({percentage:.1f}%)"
                )
                if verbosity > 0:
                    console.print(
                        f"    {_make_progress_bar(width, bar_width, 'green')}"
                    )

            # Show other counts with normalized width
            for ret, count in sorted(
                ((k, v) for k, v in rets.items() if k is not None),
                key=lambda x: x[0] or "",
            ):
                percentage = count / grand_total * 100
                bar_width = int((count / global_max) * width)
                terminalreporter.write_line(f"    {ret}: {count} ({percentage:.1f}%)")
                if verbosity > 0:
                    console.print(f"    {_make_progress_bar(width, bar_width, 'red')}")

            terminalreporter.write_line("")


def _make_progress_bar(width: int, filled: int, color: str) -> str:
    blocks = "█" * filled + "░" * (width - filled)
    return f"[{color}]{blocks}[/]"
