from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Union

import woke.ir as ir

if TYPE_CHECKING:
    import networkx as nx

    from woke.compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from woke.config import WokeConfig


visit_map: Dict[str, Callable] = {
    "ContractDefinition": lambda self, node: self.visit_contract_definition(node),
    "EnumDefinition": lambda self, node: self.visit_enum_definition(node),
    "EnumValue": lambda self, node: self.visit_enum_value(node),
    "ErrorDefinition": lambda self, node: self.visit_error_definition(node),
    "EventDefinition": lambda self, node: self.visit_event_definition(node),
    "FunctionDefinition": lambda self, node: self.visit_function_definition(node),
    "ModifierDefinition": lambda self, node: self.visit_modifier_definition(node),
    "StructDefinition": lambda self, node: self.visit_struct_definition(node),
    "UserDefinedValueTypeDefinition": lambda self, node: self.visit_user_defined_value_type_definition(
        node
    ),
    "VariableDeclaration": lambda self, node: self.visit_variable_declaration(node),
    "Assignment": lambda self, node: self.visit_assignment(node),
    "BinaryOperation": lambda self, node: self.visit_binary_operation(node),
    "Conditional": lambda self, node: self.visit_conditional(node),
    "ElementaryTypeNameExpression": lambda self, node: self.visit_elementary_type_name_expression(
        node
    ),
    "FunctionCall": lambda self, node: self.visit_function_call(node),
    "FunctionCallOptions": lambda self, node: self.visit_function_call_options(node),
    "Identifier": lambda self, node: self.visit_identifier(node),
    "IndexAccess": lambda self, node: self.visit_index_access(node),
    "IndexRangeAccess": lambda self, node: self.visit_index_range_access(node),
    "Literal": lambda self, node: self.visit_literal(node),
    "MemberAccess": lambda self, node: self.visit_member_access(node),
    "NewExpression": lambda self, node: self.visit_new_expression(node),
    "TupleExpression": lambda self, node: self.visit_tuple_expression(node),
    "UnaryOperation": lambda self, node: self.visit_unary_operation(node),
    "IdentifierPath": lambda self, node: self.visit_identifier_path(node),
    "ImportDirective": lambda self, node: self.visit_import_directive(node),
    "InheritanceSpecifier": lambda self, node: self.visit_inheritance_specifier(node),
    "ModifierInvocation": lambda self, node: self.visit_modifier_invocation(node),
    "OverrideSpecifier": lambda self, node: self.visit_override_specifier(node),
    "ParameterList": lambda self, node: self.visit_parameter_list(node),
    "PragmaDirective": lambda self, node: self.visit_pragma_directive(node),
    "SourceUnit": lambda self, node: self.visit_source_unit(node),
    "StructuredDocumentation": lambda self, node: self.visit_structured_documentation(
        node
    ),
    "TryCatchClause": lambda self, node: self.visit_try_catch_clause(node),
    "UsingForDirective": lambda self, node: self.visit_using_for_directive(node),
    "Block": lambda self, node: self.visit_block(node),
    "Break": lambda self, node: self.visit_break(node),
    "Continue": lambda self, node: self.visit_continue(node),
    "DoWhileStatement": lambda self, node: self.visit_do_while_statement(node),
    "EmitStatement": lambda self, node: self.visit_emit_statement(node),
    "ExpressionStatement": lambda self, node: self.visit_expression_statement(node),
    "ForStatement": lambda self, node: self.visit_for_statement(node),
    "IfStatement": lambda self, node: self.visit_if_statement(node),
    "InlineAssembly": lambda self, node: self.visit_inline_assembly(node),
    "PlaceholderStatement": lambda self, node: self.visit_placeholder_statement(node),
    "Return": lambda self, node: self.visit_return(node),
    "RevertStatement": lambda self, node: self.visit_revert_statement(node),
    "TryStatement": lambda self, node: self.visit_try_statement(node),
    "UncheckedBlock": lambda self, node: self.visit_unchecked_block(node),
    "VariableDeclarationStatement": lambda self, node: self.visit_variable_declaration_statement(
        node
    ),
    "WhileStatement": lambda self, node: self.visit_while_statement(node),
    "ArrayTypeName": lambda self, node: self.visit_array_type_name(node),
    "ElementaryTypeName": lambda self, node: self.visit_elementary_type_name(node),
    "FunctionTypeName": lambda self, node: self.visit_function_type_name(node),
    "Mapping": lambda self, node: self.visit_mapping(node),
    "UserDefinedTypeName": lambda self, node: self.visit_user_defined_type_name(node),
    "YulAssignment": lambda self, node: self.visit_yul_assignment(node),
    "YulBlock": lambda self, node: self.visit_yul_block(node),
    "YulBreak": lambda self, node: self.visit_yul_break(node),
    "YulCase": lambda self, node: self.visit_yul_case(node),
    "YulContinue": lambda self, node: self.visit_yul_continue(node),
    "YulExpressionStatement": lambda self, node: self.visit_yul_expression_statement(
        node
    ),
    "YulForLoop": lambda self, node: self.visit_yul_for_loop(node),
    "YulFunctionCall": lambda self, node: self.visit_yul_function_call(node),
    "YulFunctionDefinition": lambda self, node: self.visit_yul_function_definition(
        node
    ),
    "YulIdentifier": lambda self, node: self.visit_yul_identifier(node),
    "YulIf": lambda self, node: self.visit_yul_if(node),
    "YulLeave": lambda self, node: self.visit_yul_leave(node),
    "YulLiteral": lambda self, node: self.visit_yul_literal(node),
    "YulSwitch": lambda self, node: self.visit_yul_switch(node),
    "YulTypedName": lambda self, node: self.visit_yul_typed_name(node),
    "YulVariableDeclaration": lambda self, node: self.visit_yul_variable_declaration(
        node
    ),
}


class Visitor:
    build: ProjectBuild
    build_info: ProjectBuildInfo
    config: WokeConfig
    imports_graph: nx.DiGraph

    def visit_contract_definition(self, node: ir.ContractDefinition):
        pass

    def visit_enum_definition(self, node: ir.EnumDefinition):
        pass

    def visit_enum_value(self, node: ir.EnumValue):
        pass

    def visit_error_definition(self, node: ir.ErrorDefinition):
        pass

    def visit_event_definition(self, node: ir.EventDefinition):
        pass

    def visit_function_definition(self, node: ir.FunctionDefinition):
        pass

    def visit_modifier_definition(self, node: ir.ModifierDefinition):
        pass

    def visit_struct_definition(self, node: ir.StructDefinition):
        pass

    def visit_user_defined_value_type_definition(
        self, node: ir.UserDefinedValueTypeDefinition
    ):
        pass

    def visit_variable_declaration(self, node: ir.VariableDeclaration):
        pass

    # expressions
    def visit_assignment(self, node: ir.Assignment):
        pass

    def visit_binary_operation(self, node: ir.BinaryOperation):
        pass

    def visit_conditional(self, node: ir.Conditional):
        pass

    def visit_elementary_type_name_expression(
        self, node: ir.ElementaryTypeNameExpression
    ):
        pass

    def visit_function_call(self, node: ir.FunctionCall):
        pass

    def visit_function_call_options(self, node: ir.FunctionCallOptions):
        pass

    def visit_identifier(self, node: ir.Identifier):
        pass

    def visit_index_access(self, node: ir.IndexAccess):
        pass

    def visit_index_range_access(self, node: ir.IndexRangeAccess):
        pass

    def visit_literal(self, node: ir.Literal):
        pass

    def visit_member_access(self, node: ir.MemberAccess):
        pass

    def visit_new_expression(self, node: ir.NewExpression):
        pass

    def visit_tuple_expression(self, node: ir.TupleExpression):
        pass

    def visit_unary_operation(self, node: ir.UnaryOperation):
        pass

    # meta
    def visit_identifier_path(self, node: ir.IdentifierPath):
        pass

    def visit_import_directive(self, node: ir.ImportDirective):
        pass

    def visit_inheritance_specifier(self, node: ir.InheritanceSpecifier):
        pass

    def visit_modifier_invocation(self, node: ir.ModifierInvocation):
        pass

    def visit_override_specifier(self, node: ir.OverrideSpecifier):
        pass

    def visit_parameter_list(self, node: ir.ParameterList):
        pass

    def visit_pragma_directive(self, node: ir.PragmaDirective):
        pass

    def visit_source_unit(self, node: ir.SourceUnit):
        pass

    def visit_structured_documentation(self, node: ir.StructuredDocumentation):
        pass

    def visit_try_catch_clause(self, node: ir.TryCatchClause):
        pass

    def visit_using_for_directive(self, node: ir.UsingForDirective):
        pass

    # statements
    def visit_block(self, node: ir.Block):
        pass

    def visit_break(self, node: ir.Break):
        pass

    def visit_continue(self, node: ir.Continue):
        pass

    def visit_do_while_statement(self, node: ir.DoWhileStatement):
        pass

    def visit_emit_statement(self, node: ir.EmitStatement):
        pass

    def visit_expression_statement(self, node: ir.ExpressionStatement):
        pass

    def visit_for_statement(self, node: ir.ForStatement):
        pass

    def visit_if_statement(self, node: ir.IfStatement):
        pass

    def visit_inline_assembly(self, node: ir.InlineAssembly):
        pass

    def visit_placeholder_statement(self, node: ir.PlaceholderStatement):
        pass

    def visit_return(self, node: ir.Return):
        pass

    def visit_revert_statement(self, node: ir.RevertStatement):
        pass

    def visit_try_statement(self, node: ir.TryStatement):
        pass

    def visit_unchecked_block(self, node: ir.UncheckedBlock):
        pass

    def visit_variable_declaration_statement(
        self, node: ir.VariableDeclarationStatement
    ):
        pass

    def visit_while_statement(self, node: ir.WhileStatement):
        pass

    # type names
    def visit_array_type_name(self, node: ir.ArrayTypeName):
        pass

    def visit_elementary_type_name(self, node: ir.ElementaryTypeName):
        pass

    def visit_function_type_name(self, node: ir.FunctionTypeName):
        pass

    def visit_mapping(self, node: ir.Mapping):
        pass

    def visit_user_defined_type_name(self, node: ir.UserDefinedTypeName):
        pass

    # yul
    def visit_yul_assignment(self, node: ir.YulAssignment):
        pass

    def visit_yul_block(self, node: ir.YulBlock):
        pass

    def visit_yul_break(self, node: ir.YulBreak):
        pass

    def visit_yul_case(self, node: ir.YulCase):
        pass

    def visit_yul_continue(self, node: ir.YulContinue):
        pass

    def visit_yul_expression_statement(self, node: ir.YulExpressionStatement):
        pass

    def visit_yul_for_loop(self, node: ir.YulForLoop):
        pass

    def visit_yul_function_call(self, node: ir.YulFunctionCall):
        pass

    def visit_yul_function_definition(self, node: ir.YulFunctionDefinition):
        pass

    def visit_yul_identifier(self, node: ir.YulIdentifier):
        pass

    def visit_yul_if(self, node: ir.YulIf):
        pass

    def visit_yul_leave(self, node: ir.YulLeave):
        pass

    def visit_yul_literal(self, node: ir.YulLiteral):
        pass

    def visit_yul_switch(self, node: ir.YulSwitch):
        pass

    def visit_yul_typed_name(self, node: ir.YulTypedName):
        pass

    def visit_yul_variable_declaration(self, node: ir.YulVariableDeclaration):
        pass

    def generate_link_from_line_col(
        self, path: Union[str, Path], line: int, col: int
    ) -> str:
        if isinstance(path, Path):
            path = str(path.resolve())
        return self.config.general.link_format.format(path=path, line=line, col=col)

    def generate_link(self, node: ir.IrAbc) -> str:
        if isinstance(node, ir.DeclarationAbc):
            line, col = node.source_unit.get_line_col_from_byte_offset(
                node.name_location[0]
            )
        else:
            line, col = node.source_unit.get_line_col_from_byte_offset(
                node.byte_location[0]
            )
        return self.generate_link_from_line_col(node.file, line, col)
