from click.core import Context
import click


@click.group()
@click.option("--debug/--no-debug", default=True)
@click.pass_context
def main(ctx: Context, debug: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
