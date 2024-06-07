import multiprocessing
import os
import threading
import traceback
from itertools import chain
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
from rich.console import Console

from wake.cli.detect import run_detect
from wake.cli.print import run_print
from wake.compiler.build_data_model import ProjectBuild, ProjectBuildInfo
from wake.config import WakeConfig
from wake.core.exceptions import ThreadCancelledError
from wake.core.lsp_provider import LspProvider
from wake.detectors import DetectorImpact
from wake.detectors.api import DetectorConfidence, DetectorResult, detect
from wake.ir import DeclarationAbc, SourceUnit
from wake.lsp.common_structures import (
    CodeDescription,
    Diagnostic,
    DiagnosticRelatedInformation,
    DiagnosticSeverity,
    DocumentUri,
    Location,
    Position,
    Range,
)
from wake.lsp.logging_handler import LspLoggingHandler
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.utils import path_to_uri
from wake.printers.api import run_printers
from wake.utils import StrEnum


class DetectionAdditionalInfo(LspModel):
    impact: DetectorImpact
    confidence: DetectorConfidence
    ignored: bool
    source_unit_name: str

    def __members(self) -> Tuple:
        return (
            self.impact,
            self.confidence,
            self.ignored,
            self.source_unit_name,
        )

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__members() == other.__members()
        return NotImplemented

    def __hash__(self):
        return hash(self.__members())


def get_range_from_byte_offsets(
    source_unit: SourceUnit, byte_offsets: Tuple[int, int]
) -> Range:
    start_line, start_col = source_unit.get_line_col_from_byte_offset(byte_offsets[0])
    end_line, end_col = source_unit.get_line_col_from_byte_offset(byte_offsets[1])
    return Range(
        start=Position(
            line=start_line - 1,
            character=start_col - 1,
        ),
        end=Position(
            line=end_line - 1,
            character=end_col - 1,
        ),
    )


def detections_to_diagnostics(
    detections: Dict[str, Tuple[List[DetectorResult], List[DetectorResult]]],
    ignored_detections_supported: bool,
) -> Dict[Path, Set[Diagnostic]]:
    errors_per_file: Dict[Path, Set[Diagnostic]] = {}

    if ignored_detections_supported:
        detection_gen = (
            (detector_name, ignored, result)
            for detector_name in detections.keys()
            for ignored, result in chain(
                ((False, r) for r in detections[detector_name][0]),
                ((True, r) for r in detections[detector_name][1]),
            )
        )
    else:
        detection_gen = (
            (detector_name, False, result)
            for detector_name in detections.keys()
            for result in detections[detector_name][0]
        )

    for detector_name, ignored, result in detection_gen:
        file = result.detection.ir_node.source_unit.file
        if len(result.detection.subdetections) > 0:
            related_info = [
                DiagnosticRelatedInformation(
                    location=Location(
                        uri=DocumentUri(path_to_uri(info.ir_node.source_unit.file)),
                        range=get_range_from_byte_offsets(
                            info.ir_node.source_unit,
                            info.lsp_range
                            if info.lsp_range is not None
                            else info.ir_node.name_location
                            if isinstance(info.ir_node, DeclarationAbc)
                            else info.ir_node.byte_location,
                        ),
                    ),
                    message=info.message,
                )
                for info in result.detection.subdetections
            ]
        else:
            related_info = None

        if file not in errors_per_file:
            errors_per_file[file] = set()
        errors_per_file[file].add(
            Diagnostic(
                range=get_range_from_byte_offsets(
                    result.detection.ir_node.source_unit,
                    result.detection.lsp_range
                    if result.detection.lsp_range is not None
                    else result.detection.ir_node.name_location
                    if isinstance(result.detection.ir_node, DeclarationAbc)
                    else result.detection.ir_node.byte_location,
                ),
                severity=(
                    DiagnosticSeverity.INFORMATION
                    if result.impact == DetectorImpact.INFO
                    else DiagnosticSeverity.WARNING
                    if result.impact == DetectorImpact.WARNING
                    else DiagnosticSeverity.ERROR
                ),
                source="Wake",
                message=result.detection.message,
                code=detector_name,
                related_information=related_info,
                code_description=CodeDescription(
                    href=result.uri,  # pyright: ignore reportGeneralTypeIssues
                )
                if result.uri is not None
                else None,
                data=DetectionAdditionalInfo(
                    confidence=result.confidence,
                    impact=result.impact,
                    source_unit_name=result.detection.ir_node.source_unit.source_unit_name,
                    ignored=ignored,
                ),
            )
        )

    return errors_per_file


class SubprocessCommandType(StrEnum):
    CONFIG = "config"
    BUILD = "build"
    RUN_DETECTORS = "run_detectors"
    DETECTORS_SUCCESS = "detectors_success"
    DETECTORS_FAILURE = "detectors_failure"
    DETECTORS_CANCELLED = "detectors_cancelled"
    RUN_DETECTOR_CALLBACK = "run_detector_callback"
    DETECTOR_CALLBACK_SUCCESS = "detector_callback_success"
    DETECTOR_CALLBACK_FAILURE = "detector_callback_failure"
    RUN_PRINTERS = "run_printers"
    PRINTERS_SUCCESS = "printers_success"
    PRINTERS_FAILURE = "printers_failure"
    PRINTERS_CANCELLED = "printers_cancelled"
    RUN_PRINTER_CALLBACK = "run_printer_callback"
    PRINTER_CALLBACK_SUCCESS = "printer_callback_success"
    PRINTER_CALLBACK_FAILURE = "printer_callback_failure"


def run_detectors_thread(
    failed_plugin_entry_points: List[Tuple[str, str]],
    failed_plugin_paths: List[Tuple[Path, str]],
    out_queue: multiprocessing.Queue,
    config: WakeConfig,
    ignored_detections_supported: bool,
    command_id: int,
    detector_names: List[str],
    detectors_provider: LspProvider,
    last_build: ProjectBuild,
    last_build_info: ProjectBuildInfo,
    last_graph: nx.DiGraph,
    detectors_thread_event: threading.Event,
):
    detectors_provider.clear()

    try:
        logging_buffer = []
        logging_handler = LspLoggingHandler(logging_buffer)

        _, detections, detector_exceptions = detect(
            detector_names,
            last_build,
            last_build_info,
            last_graph,
            config,
            None,
            detectors_provider,
            verify_paths=False,
            capture_exceptions=True,
            logging_handler=logging_handler,
            extra={"lsp": True},
            cancel_event=detectors_thread_event,
        )
        exceptions = {name: repr(e) for name, e in detector_exceptions.items()}

        out_queue.put(
            (
                SubprocessCommandType.DETECTORS_SUCCESS,
                command_id,
                (
                    failed_plugin_entry_points,
                    failed_plugin_paths,
                    detections_to_diagnostics(detections, ignored_detections_supported),
                    exceptions,
                    logging_buffer,
                    detectors_provider.get_commands(),
                    detectors_provider._code_lenses,
                    detectors_provider._hovers,
                    detectors_provider._inlay_hints,
                ),
            )
        )
    except ThreadCancelledError:
        out_queue.put((SubprocessCommandType.DETECTORS_CANCELLED, command_id, None))
    except Exception:
        out_queue.put(
            (
                SubprocessCommandType.DETECTORS_FAILURE,
                command_id,
                traceback.format_exc(),
            )
        )
    finally:
        detectors_provider.clear_commands()


def run_printers_thread(
    failed_plugin_entry_points: List[Tuple[str, str]],
    failed_plugin_paths: List[Tuple[Path, str]],
    out_queue: multiprocessing.Queue,
    config: WakeConfig,
    command_id: int,
    printer_names: List[str],
    printers_provider: LspProvider,
    last_build: ProjectBuild,
    last_build_info: ProjectBuildInfo,
    last_graph: nx.DiGraph,
    printers_thread_event: threading.Event,
):
    printers_provider.clear()

    try:
        logging_buffer = []
        logging_handler = LspLoggingHandler(logging_buffer)

        with open(os.devnull, "w") as devnull:
            console = Console(file=devnull)

            _, printer_exceptions = run_printers(
                printer_names,
                last_build,
                last_build_info,
                last_graph,
                config,
                console,
                None,
                printers_provider,
                verify_paths=False,
                capture_exceptions=True,
                logging_handler=logging_handler,
                extra={"lsp": True},
                cancel_event=printers_thread_event,
            )
        exceptions = {name: repr(e) for name, e in printer_exceptions.items()}

        out_queue.put(
            (
                SubprocessCommandType.PRINTERS_SUCCESS,
                command_id,
                (
                    failed_plugin_entry_points,
                    failed_plugin_paths,
                    exceptions,
                    logging_buffer,
                    printers_provider.get_commands(),
                    printers_provider._code_lenses,
                    printers_provider._hovers,
                    printers_provider._inlay_hints,
                ),
            )
        )
    except ThreadCancelledError:
        out_queue.put((SubprocessCommandType.PRINTERS_CANCELLED, command_id, None))
    except Exception:
        out_queue.put(
            (SubprocessCommandType.PRINTERS_FAILURE, command_id, traceback.format_exc())
        )
    finally:
        printers_provider.clear_commands()


def run_detectors_subprocess(
    in_queue: multiprocessing.Queue,
    out_queue: multiprocessing.Queue,
    config: WakeConfig,
    ignored_detections_supported: bool,
):
    last_build: Optional[ProjectBuild] = None
    last_build_info: Optional[ProjectBuildInfo] = None
    last_graph: Optional[nx.DiGraph] = None

    lsp_provider = LspProvider("detector")

    thread: Optional[threading.Thread] = None
    thread_event = threading.Event()

    run_detectors = False
    run_detectors_command_ids = []

    while True:
        command, command_id, data = in_queue.get()

        if command == SubprocessCommandType.CONFIG:
            config = data
        elif command == SubprocessCommandType.BUILD:
            last_build, last_build_info, last_graph = data
        elif command == SubprocessCommandType.RUN_DETECTORS:
            thread_event.set()
            run_detectors = True
            run_detectors_command_ids.append(command_id)
        elif command == SubprocessCommandType.RUN_DETECTOR_CALLBACK:
            callback_id = data
            try:
                detector_name, callback = lsp_provider.get_callback(callback_id)
                lsp_provider._current_sort_tag = detector_name
                callback()
                out_queue.put(
                    (
                        SubprocessCommandType.DETECTOR_CALLBACK_SUCCESS,
                        command_id,
                        lsp_provider.get_commands(),
                    )
                )
            except Exception:
                out_queue.put(
                    (
                        SubprocessCommandType.DETECTOR_CALLBACK_FAILURE,
                        command_id,
                        traceback.format_exc(),
                    )
                )
            finally:
                lsp_provider.clear_commands()
        else:
            pass

        if in_queue.empty() and run_detectors:
            if thread is not None:
                thread_event.set()
                thread.join()

            thread_event.clear()

            for command_id in run_detectors_command_ids[:-1]:
                out_queue.put(
                    (SubprocessCommandType.DETECTORS_CANCELLED, command_id, None)
                )

            assert last_build is not None
            assert last_build_info is not None
            assert last_graph is not None

            # discover detectors
            all_detectors = run_detect.list_commands(
                None,  # pyright: ignore reportGeneralTypeIssues
                plugin_paths={  # pyright: ignore reportGeneralTypeIssues
                    config.project_root_path / "detectors"
                },
                force_load_plugins=True,  # pyright: ignore reportGeneralTypeIssues
                verify_paths=False,  # pyright: ignore reportGeneralTypeIssues
            )

            detectors_thread = threading.Thread(
                target=run_detectors_thread,
                args=(
                    [
                        (package, repr(e))
                        for package, e in run_detect.failed_plugin_entry_points
                    ],
                    [(path, repr(e)) for path, e in run_detect.failed_plugin_paths],
                    out_queue,
                    config,
                    ignored_detections_supported,
                    run_detectors_command_ids[-1],
                    all_detectors,
                    lsp_provider,
                    last_build,
                    last_build_info,
                    last_graph,
                    thread_event,
                ),
            )
            detectors_thread.start()

            run_detectors = False
            run_detectors_command_ids = []


def run_printers_subprocess(
    in_queue: multiprocessing.Queue,
    out_queue: multiprocessing.Queue,
    config: WakeConfig,
):
    last_build: Optional[ProjectBuild] = None
    last_build_info: Optional[ProjectBuildInfo] = None
    last_graph: Optional[nx.DiGraph] = None

    lsp_provider = LspProvider("printer")

    thread: Optional[threading.Thread] = None
    thread_event = threading.Event()

    run_printers = False
    run_printers_command_ids = []

    while True:
        command, command_id, data = in_queue.get()

        if command == SubprocessCommandType.CONFIG:
            config = data
        elif command == SubprocessCommandType.BUILD:
            last_build, last_build_info, last_graph = data
        elif command == SubprocessCommandType.RUN_PRINTERS:
            thread_event.set()
            run_printers = True
            run_printers_command_ids.append(command_id)
        elif command == SubprocessCommandType.RUN_PRINTER_CALLBACK:
            callback_id = data
            try:
                printer_name, callback = lsp_provider.get_callback(callback_id)
                lsp_provider._current_sort_tag = printer_name
                callback()
                out_queue.put(
                    (
                        SubprocessCommandType.PRINTER_CALLBACK_SUCCESS,
                        command_id,
                        lsp_provider.get_commands(),
                    )
                )
            except Exception:
                out_queue.put(
                    (
                        SubprocessCommandType.PRINTER_CALLBACK_FAILURE,
                        command_id,
                        traceback.format_exc(),
                    )
                )
            finally:
                lsp_provider.clear_commands()
        else:
            pass

        if in_queue.empty() and run_printers:
            if thread is not None:
                thread_event.set()
                thread.join()

            thread_event.clear()

            for command_id in run_printers_command_ids[:-1]:
                out_queue.put(
                    (SubprocessCommandType.PRINTERS_CANCELLED, command_id, None)
                )

            assert last_build is not None
            assert last_build_info is not None
            assert last_graph is not None

            all_printers = run_print.list_commands(
                None,  # pyright: ignore reportGeneralTypeIssues
                plugin_paths={  # pyright: ignore reportGeneralTypeIssues
                    config.project_root_path / "printers"
                },
                force_load_plugins=True,  # pyright: ignore reportGeneralTypeIssues
                verify_paths=False,  # pyright: ignore reportGeneralTypeIssues
            )

            printers_thread = threading.Thread(
                target=run_printers_thread,
                args=(
                    [
                        (package, repr(e))
                        for package, e in run_print.failed_plugin_entry_points
                    ],
                    [(path, repr(e)) for path, e in run_print.failed_plugin_paths],
                    out_queue,
                    config,
                    run_printers_command_ids[-1],
                    all_printers,
                    lsp_provider,
                    last_build,
                    last_build_info,
                    last_graph,
                    thread_event,
                ),
            )
            printers_thread.start()

            run_printers = False
            run_printers_command_ids = []
