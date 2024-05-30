from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import rich_click as click

from wake.core import get_logger

if TYPE_CHECKING:
    from wake.config import WakeConfig


logger = get_logger(__name__)


async def run_server(config: WakeConfig, port: int) -> None:
    from wake.lsp.server import LspServer

    async def client_callback(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        lsp_server = LspServer(config, reader, writer)
        logger.info("Client connected")
        try:
            await lsp_server.run()
        finally:
            await lsp_server.close()
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
    from wake.config import WakeConfig

    config = WakeConfig(local_config_path=context.obj.get("local_config_path", None))
    config.load_configs()

    asyncio.run(run_server(config, port))
