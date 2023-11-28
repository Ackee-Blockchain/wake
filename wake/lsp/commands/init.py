from pathlib import Path

from wake.cli.detect import run_detect
from wake.cli.print import run_print
from wake.detectors.api import init_detector
from wake.lsp.common_structures import MessageType
from wake.lsp.context import LspContext
from wake.lsp.exceptions import LspError
from wake.lsp.protocol_structures import ErrorCodes
from wake.printers.api import init_printer


async def init_detector_handler(context: LspContext, name: str, global_: bool) -> str:
    async def module_name_error_callback(module_name: str) -> None:
        raise LspError(
            ErrorCodes.InvalidParams,
            f"Detector name must be a valid Python identifier, got {name}",
        )

    async def detector_overwrite_callback(path: Path) -> None:
        raise LspError(ErrorCodes.RequestFailed, f"File {path} already exists.")

    async def detector_exists_callback(other: str) -> None:
        if (
            await context.server.show_message_request(
                f"Detector {name} already exists in {other}. Create anyway?",
                MessageType.INFO,
                ["Yes", "No"],
            )
            != "Yes"
        ):
            raise RuntimeError()

    # dummy call to load all detectors
    run_detect.list_commands(
        None,  # pyright: ignore reportGeneralTypeIssues
        plugin_paths={  # pyright: ignore reportGeneralTypeIssues
            context.config.project_root_path / "detectors"
        },
        force_load_plugins=True,  # pyright: ignore reportGeneralTypeIssues
        verify_paths=False,  # pyright: ignore reportGeneralTypeIssues
    )

    try:
        detector_path = await init_detector(
            context.config,
            name,
            global_,
            module_name_error_callback,
            detector_overwrite_callback,
            detector_exists_callback,
        )
    except RuntimeError:
        # user did not approve creation of the detector with the duplicate name
        return ""

    await context.server.show_message(
        f"Detector {name} created at {detector_path}.",
        MessageType.INFO,
    )
    await context.server.log_message(
        f"Detector {name} created at {detector_path}.",
        MessageType.INFO,
    )
    return str(detector_path)


async def init_printer_handler(context: LspContext, name: str, global_: bool) -> str:
    async def module_name_error_callback(module_name: str) -> None:
        raise LspError(
            ErrorCodes.InvalidParams,
            f"Printer name must be a valid Python identifier, got {name}",
        )

    async def printer_overwrite_callback(path: Path) -> None:
        raise LspError(ErrorCodes.RequestFailed, f"File {path} already exists.")

    async def printer_exists_callback(other: str) -> None:
        if (
            await context.server.show_message_request(
                f"Printer {name} already exists in {other}. Create anyway?",
                MessageType.INFO,
                ["Yes", "No"],
            )
            != "Yes"
        ):
            raise RuntimeError()

    # dummy call to make sure all printers are loaded
    run_print.list_commands(
        None,  # pyright: ignore reportGeneralTypeIssues
        plugin_paths={  # pyright: ignore reportGeneralTypeIssues
            context.config.project_root_path / "printers"
        },
        force_load_plugins=True,  # pyright: ignore reportGeneralTypeIssues
        verify_paths=False,  # pyright: ignore reportGeneralTypeIssues
    )

    try:
        printer_path: Path = await init_printer(
            context.config,
            name,
            global_,
            module_name_error_callback,
            printer_overwrite_callback,
            printer_exists_callback,
        )
    except RuntimeError:
        # user did not approve creation of the printer with the duplicate name
        return ""

    await context.server.show_message(
        f"Printer {name} created at {printer_path}.",
        MessageType.INFO,
    )
    await context.server.log_message(
        f"Printer {name} created at {printer_path}.",
        MessageType.INFO,
    )
    return str(printer_path)
