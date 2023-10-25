from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import rich_click as click

from woke.core import get_logger

if TYPE_CHECKING:
    from woke.config import WokeConfig


logger = get_logger(__name__)


async def run_server(config: WokeConfig, port: int) -> None:
    from woke.lsp.server import LspServer

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
@click.option(
    "--port",
    default=65432,
    type=int,
    help="Port to listen on.",
    show_default=True,
)
@click.pass_context
def run_lsp(context: click.Context, port: int):
    """
    Start the LSP server.
    """
    from woke.config import WokeConfig

    config = WokeConfig()
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    asyncio.run(run_server(config, port))
