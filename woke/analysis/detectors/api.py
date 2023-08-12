from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, DefaultDict, Dict, List, Optional, Tuple, Type, Union

import rich.console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax, SyntaxTheme
from rich.tree import Tree

import woke.cli.console
from woke.config import WokeConfig
from woke.ir import *
from woke.utils.file_utils import is_relative_to

logger = logging.getLogger(__name__)


detectors: List[Detector] = []

visit_map: Dict[Type[IrAbc], Callable] = {
    ContractDefinition: lambda self, node: self.visit_contract_definition(node),
    EnumDefinition: lambda self, node: self.visit_enum_definition(node),
    EnumValue: lambda self, node: self.visit_enum_value(node),
    ErrorDefinition: lambda self, node: self.visit_error_definition(node),
    EventDefinition: lambda self, node: self.visit_event_definition(node),
    FunctionDefinition: lambda self, node: self.visit_function_definition(node),
    ModifierDefinition: lambda self, node: self.visit_modifier_definition(node),
    StructDefinition: lambda self, node: self.visit_struct_definition(node),
    UserDefinedValueTypeDefinition: lambda self, node: self.visit_user_defined_value_type_definition(
        node
    ),
    VariableDeclaration: lambda self, node: self.visit_variable_declaration(node),
    Assignment: lambda self, node: self.visit_assignment(node),
    BinaryOperation: lambda self, node: self.visit_binary_operation(node),
    Conditional: lambda self, node: self.visit_conditional(node),
    ElementaryTypeNameExpression: lambda self, node: self.visit_elementary_type_name_expression(
        node
    ),
    FunctionCall: lambda self, node: self.visit_function_call(node),
    FunctionCallOptions: lambda self, node: self.visit_function_call_options(node),
    Identifier: lambda self, node: self.visit_identifier(node),
    IndexAccess: lambda self, node: self.visit_index_access(node),
    IndexRangeAccess: lambda self, node: self.visit_index_range_access(node),
    Literal: lambda self, node: self.visit_literal(node),
    MemberAccess: lambda self, node: self.visit_member_access(node),
    NewExpression: lambda self, node: self.visit_new_expression(node),
    TupleExpression: lambda self, node: self.visit_tuple_expression(node),
    UnaryOperation: lambda self, node: self.visit_unary_operation(node),
    IdentifierPath: lambda self, node: self.visit_identifier_path(node),
    ImportDirective: lambda self, node: self.visit_import_directive(node),
    InheritanceSpecifier: lambda self, node: self.visit_inheritance_specifier(node),
    ModifierInvocation: lambda self, node: self.visit_modifier_invocation(node),
    OverrideSpecifier: lambda self, node: self.visit_override_specifier(node),
    ParameterList: lambda self, node: self.visit_parameter_list(node),
    PragmaDirective: lambda self, node: self.visit_pragma_directive(node),
    SourceUnit: lambda self, node: self.visit_source_unit(node),
    StructuredDocumentation: lambda self, node: self.visit_structured_documentation(
        node
    ),
    TryCatchClause: lambda self, node: self.visit_try_catch_clause(node),
    UsingForDirective: lambda self, node: self.visit_using_for_directive(node),
    Block: lambda self, node: self.visit_block(node),
    Break: lambda self, node: self.visit_break(node),
    Continue: lambda self, node: self.visit_continue(node),
    DoWhileStatement: lambda self, node: self.visit_do_while_statement(node),
    EmitStatement: lambda self, node: self.visit_emit_statement(node),
    ExpressionStatement: lambda self, node: self.visit_expression_statement(node),
    ForStatement: lambda self, node: self.visit_for_statement(node),
    IfStatement: lambda self, node: self.visit_if_statement(node),
    InlineAssembly: lambda self, node: self.visit_inline_assembly(node),
    PlaceholderStatement: lambda self, node: self.visit_placeholder_statement(node),
    Return: lambda self, node: self.visit_return(node),
    RevertStatement: lambda self, node: self.visit_revert_statement(node),
    TryStatement: lambda self, node: self.visit_try_statement(node),
    UncheckedBlock: lambda self, node: self.visit_unchecked_block(node),
    VariableDeclarationStatement: lambda self, node: self.visit_variable_declaration_statement(
        node
    ),
    WhileStatement: lambda self, node: self.visit_while_statement(node),
    ArrayTypeName: lambda self, node: self.visit_array_type_name(node),
    ElementaryTypeName: lambda self, node: self.visit_elementary_type_name(node),
    FunctionTypeName: lambda self, node: self.visit_function_type_name(node),
    Mapping: lambda self, node: self.visit_mapping(node),
    UserDefinedTypeName: lambda self, node: self.visit_user_defined_type_name(node),
    YulAssignment: lambda self, node: self.visit_yul_assignment(node),
    YulBlock: lambda self, node: self.visit_yul_block(node),
    YulBreak: lambda self, node: self.visit_yul_break(node),
    YulCase: lambda self, node: self.visit_yul_case(node),
    YulContinue: lambda self, node: self.visit_yul_continue(node),
    YulExpressionStatement: lambda self, node: self.visit_yul_expression_statement(
        node
    ),
    YulForLoop: lambda self, node: self.visit_yul_for_loop(node),
    YulFunctionCall: lambda self, node: self.visit_yul_function_call(node),
    YulFunctionDefinition: lambda self, node: self.visit_yul_function_definition(node),
    YulIdentifier: lambda self, node: self.visit_yul_identifier(node),
    YulIf: lambda self, node: self.visit_yul_if(node),
    YulLeave: lambda self, node: self.visit_yul_leave(node),
    YulLiteral: lambda self, node: self.visit_yul_literal(node),
    YulSwitch: lambda self, node: self.visit_yul_switch(node),
    YulTypedName: lambda self, node: self.visit_yul_typed_name(node),
    YulVariableDeclaration: lambda self, node: self.visit_yul_variable_declaration(
        node
    ),
}


@dataclass(eq=True, frozen=True)
class DetectorResult:
    ir_node: IrAbc
    message: str
    related_info: Tuple[DetectorResult, ...] = field(default_factory=tuple)
    lsp_range: Optional[Tuple[int, int]] = field(default=None)


@dataclass
class DetectionResult:
    result: DetectorResult
    code: int
    string_id: str


@dataclass
class Detector:
    code: int
    string_id: str
    detector: Type[DetectorAbc]


class DetectorAbc(ABC):
    @abstractmethod
    def report(self) -> List[DetectorResult]:
        ...

    # declarations
    def visit_contract_definition(self, node: ContractDefinition):
        pass

    def visit_enum_definition(self, node: EnumDefinition):
        pass

    def visit_enum_value(self, node: EnumValue):
        pass

    def visit_error_definition(self, node: ErrorDefinition):
        pass

    def visit_event_definition(self, node: EventDefinition):
        pass

    def visit_function_definition(self, node: FunctionDefinition):
        pass

    def visit_modifier_definition(self, node: ModifierDefinition):
        pass

    def visit_struct_definition(self, node: StructDefinition):
        pass

    def visit_user_defined_value_type_definition(
        self, node: UserDefinedValueTypeDefinition
    ):
        pass

    def visit_variable_declaration(self, node: VariableDeclaration):
        pass

    # expressions
    def visit_assignment(self, node: Assignment):
        pass

    def visit_binary_operation(self, node: BinaryOperation):
        pass

    def visit_conditional(self, node: Conditional):
        pass

    def visit_elementary_type_name_expression(self, node: ElementaryTypeNameExpression):
        pass

    def visit_function_call(self, node: FunctionCall):
        pass

    def visit_function_call_options(self, node: FunctionCallOptions):
        pass

    def visit_identifier(self, node: Identifier):
        pass

    def visit_index_access(self, node: IndexAccess):
        pass

    def visit_index_range_access(self, node: IndexRangeAccess):
        pass

    def visit_literal(self, node: Literal):
        pass

    def visit_member_access(self, node: MemberAccess):
        pass

    def visit_new_expression(self, node: NewExpression):
        pass

    def visit_tuple_expression(self, node: TupleExpression):
        pass

    def visit_unary_operation(self, node: UnaryOperation):
        pass

    # meta
    def visit_identifier_path(self, node: IdentifierPath):
        pass

    def visit_import_directive(self, node: ImportDirective):
        pass

    def visit_inheritance_specifier(self, node: InheritanceSpecifier):
        pass

    def visit_modifier_invocation(self, node: ModifierInvocation):
        pass

    def visit_override_specifier(self, node: OverrideSpecifier):
        pass

    def visit_parameter_list(self, node: ParameterList):
        pass

    def visit_pragma_directive(self, node: PragmaDirective):
        pass

    def visit_source_unit(self, node: SourceUnit):
        pass

    def visit_structured_documentation(self, node: StructuredDocumentation):
        pass

    def visit_try_catch_clause(self, node: TryCatchClause):
        pass

    def visit_using_for_directive(self, node: UsingForDirective):
        pass

    # statements
    def visit_block(self, node: Block):
        pass

    def visit_break(self, node: Break):
        pass

    def visit_continue(self, node: Continue):
        pass

    def visit_do_while_statement(self, node: DoWhileStatement):
        pass

    def visit_emit_statement(self, node: EmitStatement):
        pass

    def visit_expression_statement(self, node: ExpressionStatement):
        pass

    def visit_for_statement(self, node: ForStatement):
        pass

    def visit_if_statement(self, node: IfStatement):
        pass

    def visit_inline_assembly(self, node: InlineAssembly):
        pass

    def visit_placeholder_statement(self, node: PlaceholderStatement):
        pass

    def visit_return(self, node: Return):
        pass

    def visit_revert_statement(self, node: RevertStatement):
        pass

    def visit_try_statement(self, node: TryStatement):
        pass

    def visit_unchecked_block(self, node: UncheckedBlock):
        pass

    def visit_variable_declaration_statement(self, node: VariableDeclarationStatement):
        pass

    def visit_while_statement(self, node: WhileStatement):
        pass

    # type names
    def visit_array_type_name(self, node: ArrayTypeName):
        pass

    def visit_elementary_type_name(self, node: ElementaryTypeName):
        pass

    def visit_function_type_name(self, node: FunctionTypeName):
        pass

    def visit_mapping(self, node: Mapping):
        pass

    def visit_user_defined_type_name(self, node: UserDefinedTypeName):
        pass

    # yul
    def visit_yul_assignment(self, node: YulAssignment):
        pass

    def visit_yul_block(self, node: YulBlock):
        pass

    def visit_yul_break(self, node: YulBreak):
        pass

    def visit_yul_case(self, node: YulCase):
        pass

    def visit_yul_continue(self, node: YulContinue):
        pass

    def visit_yul_expression_statement(self, node: YulExpressionStatement):
        pass

    def visit_yul_for_loop(self, node: YulForLoop):
        pass

    def visit_yul_function_call(self, node: YulFunctionCall):
        pass

    def visit_yul_function_definition(self, node: YulFunctionDefinition):
        pass

    def visit_yul_identifier(self, node: YulIdentifier):
        pass

    def visit_yul_if(self, node: YulIf):
        pass

    def visit_yul_leave(self, node: YulLeave):
        pass

    def visit_yul_literal(self, node: YulLiteral):
        pass

    def visit_yul_switch(self, node: YulSwitch):
        pass

    def visit_yul_typed_name(self, node: YulTypedName):
        pass

    def visit_yul_variable_declaration(self, node: YulVariableDeclaration):
        pass


def _get_enabled_detectors(config: WokeConfig) -> List[Detector]:
    ret = []
    for d in detectors:
        if (
            config.detectors.only is not None
            and d.string_id not in config.detectors.only
        ):
            continue
        if (
            d.string_id not in config.detectors.exclude
            and d.code not in config.detectors.exclude
        ):
            ret.append(d)
    return ret


def detect(
    config: WokeConfig,
    source_units: Dict[Path, SourceUnit],
    *,
    console: Optional[rich.console.Console] = None,
) -> List[DetectionResult]:
    def _detection_ignored(detection: DetectorResult) -> bool:
        return any(
            is_relative_to(detection.ir_node.file, p)
            for p in config.detectors.ignore_paths
        ) and all(_detection_ignored(d) for d in detection.related_info)

    results: DefaultDict[str, DefaultDict[str, List[DetectionResult]]] = defaultdict(
        lambda: defaultdict(list)
    )
    enabled_detectors = []
    enabled_detector_instances = []
    for d in _get_enabled_detectors(config):
        enabled_detectors.append(d)
        enabled_detector_instances.append(d.detector())

    path_to_source_unit_name: Dict[Path, str] = {}

    if console is not None:
        original_record = console.record
        console.record = False
        ctx_manager = console.status("[bold green]Running detectors...")
    else:
        original_record = True
        ctx_manager = nullcontext()
    with ctx_manager as s:
        for path, source_unit in source_units.items():
            if s is not None:
                s.update(f"[bold green]Detecting in {source_unit.source_unit_name}...")
            path_to_source_unit_name[path] = source_unit.source_unit_name
            for ir_node in source_unit:
                for d, detector_instance in zip(
                    enabled_detectors, enabled_detector_instances
                ):
                    visit_map[ir_node.__class__](detector_instance, ir_node)

    if console is not None:
        console.record = original_record

    for d, detector_instance in zip(enabled_detectors, enabled_detector_instances):
        for result in detector_instance.report():
            if not _detection_ignored(result):
                results[d.string_id][
                    path_to_source_unit_name[result.ir_node.file]
                ].append(
                    DetectionResult(
                        result=result,
                        code=d.code,
                        string_id=d.string_id,
                    )
                )

    ret = []
    sorted_detectors = sorted(results.keys())
    for detector_id in sorted_detectors:
        sorted_files = sorted(results[detector_id].keys())
        for file in sorted_files:
            ret.extend(
                sorted(
                    results[detector_id][file],
                    key=lambda d: d.result.ir_node.byte_location[0],
                )
            )
    return ret


def print_detectors(config: WokeConfig, theme: str = "monokai") -> None:
    applied_detectors = set()
    for d in _get_enabled_detectors(config):
        applied_detectors.add((d.string_id, d.detector.__doc__))

    detectors_list = "Using the following detectors:\n- " + "\n- ".join(
        f"{d[0]}\n\t{d[1]}" for d in sorted(applied_detectors)
    )
    woke.cli.console.console.print(
        Markdown(detectors_list, inline_code_theme=theme, inline_code_lexer="solidity")
    )


def print_detection(
    result: DetectionResult, theme: Union[str, SyntaxTheme] = "monokai"
) -> None:
    def print_result(
        detector_result: DetectorResult,
        tree: Optional[Tree],
        detector_id: Optional[str],
    ) -> Tree:
        source_unit = detector_result.ir_node
        while source_unit is not None:
            if isinstance(source_unit, SourceUnit):
                break
            source_unit = source_unit.parent
        assert isinstance(source_unit, SourceUnit)

        tmp_lines = re.split(b"(\r?\n)", source_unit.file_source)
        lines: List[bytes] = []
        for line in tmp_lines:
            if line in {b"\r\n", b"\n"}:
                lines[-1] += line
            else:
                lines.append(line)

        offset = 0
        line_index = 0
        while offset <= detector_result.ir_node.byte_location[0]:
            offset += len(lines[line_index])
            line_index += 1
        line_index -= 1

        source = ""
        start_line_index = max(0, line_index - 3)
        end_line_index = min(len(lines), line_index + 3)
        for i in range(start_line_index, end_line_index):
            source += lines[i].decode("utf-8")

        panel = Panel.fit(
            Syntax(
                source,
                "solidity",
                theme=theme,
                line_numbers=True,
                start_line=(start_line_index + 1),
                highlight_lines={line_index + 1},
            ),
            title=f"{detector_result.message} \[{detector_id}]"  # pyright: ignore reportInvalidStringEscapeSequence
            if detector_id is not None
            else detector_result.message,
            title_align="left",
            subtitle=source_unit.source_unit_name,
            subtitle_align="left",
        )

        if tree is None:
            t = Tree(panel)
        else:
            t = tree.add(panel)

        for additional_result in detector_result.related_info:
            print_result(additional_result, t, None)

        return t

    woke.cli.console.console.print("\n")
    tree = print_result(result.result, None, result.string_id)
    woke.cli.console.console.print(tree)


def detector(code: int, string_id: str):
    def decorator(d: Type[DetectorAbc]):
        detectors.append(Detector(code=code, string_id=string_id, detector=d))
        return d

    return decorator
