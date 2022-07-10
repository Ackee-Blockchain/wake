import asyncio
import logging

import click

from woke.config import WokeConfig
from woke.lsp.server import LspServer

logger = logging.getLogger(__name__)


async def run_server(config: WokeConfig, port: int) -> None:
    async def client_callback(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        lsp_server = LspServer(config, reader, writer)
        logger.info("Client connected")
        await lsp_server.run()
        writer.close()
        logger.info("Client disconnected")

    server = await asyncio.start_server(client_callback, port=port)
    logger.info(f"Started LSP server on port {port}")

    async with server:
        await server.serve_forever()


@click.command(name="lsp")
@click.option("--port", default=65432, type=int)
@click.pass_context
def run_lsp(context: click.Context, port: int):
    config = WokeConfig(woke_root_path=context.obj["woke_root_path"])
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    asyncio.run(run_server(config, port))
