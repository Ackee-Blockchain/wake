from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Union

import wake.ir as ir

if TYPE_CHECKING:
    import logging

    import networkx as nx

    from wake.compiler.build_data_model import ProjectBuild, ProjectBuildInfo
    from wake.config import WakeConfig


group_map: Dict[str, List[str]] = {
    # declarations
    "ContractDefinition": ["SolidityAbc", "DeclarationAbc"],
    "EnumDefinition": ["SolidityAbc", "DeclarationAbc"],
    "EnumValue": ["SolidityAbc", "DeclarationAbc"],
    "ErrorDefinition": ["SolidityAbc", "DeclarationAbc"],
    "EventDefinition": ["SolidityAbc", "DeclarationAbc"],
    "FunctionDefinition": ["SolidityAbc", "DeclarationAbc"],
    "ModifierDefinition": ["SolidityAbc", "DeclarationAbc"],
    "StructDefinition": ["SolidityAbc", "DeclarationAbc"],
    "UserDefinedValueTypeDefinition": ["SolidityAbc", "DeclarationAbc"],
    "VariableDeclaration": ["SolidityAbc", "DeclarationAbc"],
    # expressions
    "Assignment": ["SolidityAbc", "ExpressionAbc"],
    "BinaryOperation": ["SolidityAbc", "ExpressionAbc"],
    "Conditional": ["SolidityAbc", "ExpressionAbc"],
    "ElementaryTypeNameExpression": ["SolidityAbc", "ExpressionAbc"],
    "FunctionCall": ["SolidityAbc", "ExpressionAbc"],
    "FunctionCallOptions": ["SolidityAbc", "ExpressionAbc"],
    "Identifier": ["SolidityAbc", "ExpressionAbc"],
    "IndexAccess": ["SolidityAbc", "ExpressionAbc"],
    "IndexRangeAccess": ["SolidityAbc", "ExpressionAbc"],
    "Literal": ["SolidityAbc", "ExpressionAbc"],
    "MemberAccess": ["SolidityAbc", "ExpressionAbc"],
    "NewExpression": ["SolidityAbc", "ExpressionAbc"],
    "TupleExpression": ["SolidityAbc", "ExpressionAbc"],
    "UnaryOperation": ["SolidityAbc", "ExpressionAbc"],
    # meta
    "IdentifierPath": ["SolidityAbc"],
    "ImportDirective": ["SolidityAbc"],
    "InheritanceSpecifier": ["SolidityAbc"],
    "ModifierInvocation": ["SolidityAbc"],
    "OverrideSpecifier": ["SolidityAbc"],
    "ParameterList": ["SolidityAbc"],
    "PragmaDirective": ["SolidityAbc"],
    "SourceUnit": ["SolidityAbc"],
    "StructuredDocumentation": ["SolidityAbc"],
    "TryCatchClause": ["SolidityAbc"],
    "UsingForDirective": ["SolidityAbc"],
    # statements
    "Block": ["SolidityAbc", "StatementAbc"],
    "Break": ["SolidityAbc", "StatementAbc"],
    "Continue": ["SolidityAbc", "StatementAbc"],
    "DoWhileStatement": ["SolidityAbc", "StatementAbc"],
    "EmitStatement": ["SolidityAbc", "StatementAbc"],
    "ExpressionStatement": ["SolidityAbc", "StatementAbc"],
    "ForStatement": ["SolidityAbc", "StatementAbc"],
    "IfStatement": ["SolidityAbc", "StatementAbc"],
    "InlineAssembly": ["SolidityAbc", "StatementAbc"],
    "PlaceholderStatement": ["SolidityAbc", "StatementAbc"],
    "Return": ["SolidityAbc", "StatementAbc"],
    "RevertStatement": ["SolidityAbc", "StatementAbc"],
    "TryStatement": ["SolidityAbc", "StatementAbc"],
    "UncheckedBlock": ["SolidityAbc", "StatementAbc"],
    "VariableDeclarationStatement": ["SolidityAbc", "StatementAbc"],
    "WhileStatement": ["SolidityAbc", "StatementAbc"],
    # type names
    "ArrayTypeName": ["SolidityAbc", "TypeNameAbc"],
    "ElementaryTypeName": ["SolidityAbc", "TypeNameAbc"],
    "FunctionTypeName": ["SolidityAbc", "TypeNameAbc"],
    "Mapping": ["SolidityAbc", "TypeNameAbc"],
    "UserDefinedTypeName": ["SolidityAbc", "TypeNameAbc"],
    # yul
    "YulAssignment": ["YulAbc", "YulStatementAbc"],
    "YulBlock": ["YulAbc", "YulStatementAbc"],
    "YulBreak": ["YulAbc", "YulStatementAbc"],
    "YulCase": ["YulAbc"],
    "YulContinue": ["YulAbc", "YulStatementAbc"],
    "YulExpressionStatement": ["YulAbc", "YulStatementAbc"],
    "YulForLoop": ["YulAbc", "YulStatementAbc"],
    "YulFunctionCall": ["YulAbc"],
    "YulFunctionDefinition": ["YulAbc", "YulStatementAbc"],
    "YulIdentifier": ["YulAbc"],
    "YulIf": ["YulAbc", "YulStatementAbc"],
    "YulLeave": ["YulAbc", "YulStatementAbc"],
    "YulLiteral": ["YulAbc"],
    "YulSwitch": ["YulAbc", "YulStatementAbc"],
    "YulTypedName": ["YulAbc"],
    "YulVariableDeclaration": ["YulAbc", "YulStatementAbc"],
}


visit_map: Dict[str, Callable] = {
    "SolidityAbc": lambda self, node: self.visit_solidity_abc(node),
    "YulAbc": lambda self, node: self.visit_yul_abc(node),
    # declarations
    "DeclarationAbc": lambda self, node: self.visit_declaration_abc(node),
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
    # expressions
    "ExpressionAbc": lambda self, node: self.visit_expression_abc(node),
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
    # meta
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
    # statements
    "StatementAbc": lambda self, node: self.visit_statement_abc(node),
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
    # type names
    "TypeNameAbc": lambda self, node: self.visit_type_name_abc(node),
    "ArrayTypeName": lambda self, node: self.visit_array_type_name(node),
    "ElementaryTypeName": lambda self, node: self.visit_elementary_type_name(node),
    "FunctionTypeName": lambda self, node: self.visit_function_type_name(node),
    "Mapping": lambda self, node: self.visit_mapping(node),
    "UserDefinedTypeName": lambda self, node: self.visit_user_defined_type_name(node),
    # yul
    "YulStatementAbc": lambda self, node: self.visit_yul_statement_abc(node),
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
    """
    Base class for detectors and printers. `visit_` methods are called automatically by the execution engine.

    Attributes:
        build: The latest compilation build of the project.
        build_info: Information about the latest compilation build of the project.
        config: The loaded Wake configuration.
        imports_graph: A directed graph representing the import dependencies of the project.
            Nodes are represented by string [source unit names](https://docs.soliditylang.org/en/latest/path-resolution.html).
            Edges are directed from the imported source unit to the importing source unit.

            Nodes hold the following data attributes:

            - `path`: [Path][pathlib.Path] to the source unit file.
            - `versions`: [SolidityVersionRanges][wake.core.solidity_version.SolidityVersionRanges] describing allowed Solidity versions by pragma directives.
            - `hash`: [bytes][bytes] 256-bit BLAKE2b hash of the source unit file contents.
            - `content`: [bytes][bytes] source unit file contents.

            !!! warning
                Imports graph may contain source units that are not present in the build. This can happen for example because of a failed compilation.

        logger: A logger instance that can be used to log messages to the console. The log messages are redirected to a VS Code output window in the case of detectors running in the VS Code extension.
    """

    build: ProjectBuild
    build_info: ProjectBuildInfo
    config: WakeConfig
    imports_graph: nx.DiGraph
    logger: logging.Logger

    def visit_ir_abc(self, node: ir.IrAbc):
        """
        Visit any [IrAbc][wake.ir.abc.IrAbc] node.
        """

    def visit_solidity_abc(self, node: ir.SolidityAbc):
        """
        Visit any [SolidityAbc][wake.ir.abc.SolidityAbc] node.
        """

    def visit_yul_abc(self, node: ir.YulAbc):
        """
        Visit any [YulAbc][wake.ir.yul.abc.YulAbc] node.
        """

    def visit_yul_statement_abc(self, node: ir.YulStatementAbc):
        """
        Visit any [YulStatementAbc][wake.ir.yul.abc.YulStatementAbc] node.
        """

    # declarations
    def visit_declaration_abc(self, node: ir.DeclarationAbc):
        """
        Visit any [DeclarationAbc][wake.ir.declarations.abc.DeclarationAbc] node.
        """

    def visit_contract_definition(self, node: ir.ContractDefinition):
        """
        Visit [ContractDefinition][wake.ir.declarations.contract_definition.ContractDefinition] node.
        """

    def visit_enum_definition(self, node: ir.EnumDefinition):
        """
        Visit [EnumDefinition][wake.ir.declarations.enum_definition.EnumDefinition] node.
        """

    def visit_enum_value(self, node: ir.EnumValue):
        """
        Visit [EnumValue][wake.ir.declarations.enum_value.EnumValue] node.
        """

    def visit_error_definition(self, node: ir.ErrorDefinition):
        """
        Visit [ErrorDefinition][wake.ir.declarations.error_definition.ErrorDefinition] node.
        """

    def visit_event_definition(self, node: ir.EventDefinition):
        """
        Visit [EventDefinition][wake.ir.declarations.event_definition.EventDefinition] node.
        """

    def visit_function_definition(self, node: ir.FunctionDefinition):
        """
        Visit [FunctionDefinition][wake.ir.declarations.function_definition.FunctionDefinition] node.
        """

    def visit_modifier_definition(self, node: ir.ModifierDefinition):
        """
        Visit [ModifierDefinition][wake.ir.declarations.modifier_definition.ModifierDefinition] node.
        """

    def visit_struct_definition(self, node: ir.StructDefinition):
        """
        Visit [StructDefinition][wake.ir.declarations.struct_definition.StructDefinition] node.
        """

    def visit_user_defined_value_type_definition(
        self, node: ir.UserDefinedValueTypeDefinition
    ):
        """
        Visit [UserDefinedValueTypeDefinition][wake.ir.declarations.user_defined_value_type_definition.UserDefinedValueTypeDefinition] node.
        """

    def visit_variable_declaration(self, node: ir.VariableDeclaration):
        """
        Visit [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration] node.
        """

    # expressions
    def visit_expression_abc(self, node: ir.ExpressionAbc):
        """
        Visit any [ExpressionAbc][wake.ir.expressions.abc.ExpressionAbc] node.
        """

    def visit_assignment(self, node: ir.Assignment):
        """
        Visit [Assignment][wake.ir.expressions.assignment.Assignment] node.
        """

    def visit_binary_operation(self, node: ir.BinaryOperation):
        """
        Visit [BinaryOperation][wake.ir.expressions.binary_operation.BinaryOperation] node.
        """

    def visit_conditional(self, node: ir.Conditional):
        """
        Visit [Conditional][wake.ir.expressions.conditional.Conditional] node.
        """

    def visit_elementary_type_name_expression(
        self, node: ir.ElementaryTypeNameExpression
    ):
        """
        Visit [ElementaryTypeNameExpression][wake.ir.expressions.elementary_type_name_expression.ElementaryTypeNameExpression] node.
        """

    def visit_function_call(self, node: ir.FunctionCall):
        """
        Visit [FunctionCall][wake.ir.expressions.function_call.FunctionCall] node.
        """

    def visit_function_call_options(self, node: ir.FunctionCallOptions):
        """
        Visit [FunctionCallOptions][wake.ir.expressions.function_call_options.FunctionCallOptions] node.
        """

    def visit_identifier(self, node: ir.Identifier):
        """
        Visit [Identifier][wake.ir.expressions.identifier.Identifier] node.
        """

    def visit_index_access(self, node: ir.IndexAccess):
        """
        Visit [IndexAccess][wake.ir.expressions.index_access.IndexAccess] node.
        """

    def visit_index_range_access(self, node: ir.IndexRangeAccess):
        """
        Visit [IndexRangeAccess][wake.ir.expressions.index_range_access.IndexRangeAccess] node.
        """

    def visit_literal(self, node: ir.Literal):
        """
        Visit [Literal][wake.ir.expressions.literal.Literal] node.
        """

    def visit_member_access(self, node: ir.MemberAccess):
        """
        Visit [MemberAccess][wake.ir.expressions.member_access.MemberAccess] node.
        """

    def visit_new_expression(self, node: ir.NewExpression):
        """
        Visit [NewExpression][wake.ir.expressions.new_expression.NewExpression] node.
        """

    def visit_tuple_expression(self, node: ir.TupleExpression):
        """
        Visit [TupleExpression][wake.ir.expressions.tuple_expression.TupleExpression] node.
        """

    def visit_unary_operation(self, node: ir.UnaryOperation):
        """
        Visit [UnaryOperation][wake.ir.expressions.unary_operation.UnaryOperation] node.
        """

    # meta
    def visit_identifier_path(self, node: ir.IdentifierPath):
        """
        Visit [IdentifierPath][wake.ir.meta.identifier_path.IdentifierPath] node.
        """

    def visit_import_directive(self, node: ir.ImportDirective):
        """
        Visit [ImportDirective][wake.ir.meta.import_directive.ImportDirective] node.
        """

    def visit_inheritance_specifier(self, node: ir.InheritanceSpecifier):
        """
        Visit [InheritanceSpecifier][wake.ir.meta.inheritance_specifier.InheritanceSpecifier] node.
        """

    def visit_modifier_invocation(self, node: ir.ModifierInvocation):
        """
        Visit [ModifierInvocation][wake.ir.meta.modifier_invocation.ModifierInvocation] node.
        """

    def visit_override_specifier(self, node: ir.OverrideSpecifier):
        """
        Visit [OverrideSpecifier][wake.ir.meta.override_specifier.OverrideSpecifier] node.
        """

    def visit_parameter_list(self, node: ir.ParameterList):
        """
        Visit [ParameterList][wake.ir.meta.parameter_list.ParameterList] node.
        """

    def visit_pragma_directive(self, node: ir.PragmaDirective):
        """
        Visit [PragmaDirective][wake.ir.meta.pragma_directive.PragmaDirective] node.
        """

    def visit_source_unit(self, node: ir.SourceUnit):
        """
        Visit [SourceUnit][wake.ir.meta.source_unit.SourceUnit] node.
        """

    def visit_structured_documentation(self, node: ir.StructuredDocumentation):
        """
        Visit [StructuredDocumentation][wake.ir.meta.structured_documentation.StructuredDocumentation] node.
        """

    def visit_try_catch_clause(self, node: ir.TryCatchClause):
        """
        Visit [TryCatchClause][wake.ir.meta.try_catch_clause.TryCatchClause] node.
        """

    def visit_using_for_directive(self, node: ir.UsingForDirective):
        """
        Visit [UsingForDirective][wake.ir.meta.using_for_directive.UsingForDirective] node.
        """

    # statements
    def visit_statement_abc(self, node: ir.StatementAbc):
        """
        Visit any [StatementAbc][wake.ir.statements.abc.StatementAbc] node.
        """

    def visit_block(self, node: ir.Block):
        """
        Visit [Block][wake.ir.statements.block.Block] node.
        """

    def visit_break(self, node: ir.Break):
        """
        Visit [Break][wake.ir.statements.break_statement.Break] node.
        """

    def visit_continue(self, node: ir.Continue):
        """
        Visit [Continue][wake.ir.statements.continue_statement.Continue] node.
        """

    def visit_do_while_statement(self, node: ir.DoWhileStatement):
        """
        Visit [DoWhileStatement][wake.ir.statements.do_while_statement.DoWhileStatement] node.
        """

    def visit_emit_statement(self, node: ir.EmitStatement):
        """
        Visit [EmitStatement][wake.ir.statements.emit_statement.EmitStatement] node.
        """

    def visit_expression_statement(self, node: ir.ExpressionStatement):
        """
        Visit [ExpressionStatement][wake.ir.statements.expression_statement.ExpressionStatement] node.
        """

    def visit_for_statement(self, node: ir.ForStatement):
        """
        Visit [ForStatement][wake.ir.statements.for_statement.ForStatement] node.
        """

    def visit_if_statement(self, node: ir.IfStatement):
        """
        Visit [IfStatement][wake.ir.statements.if_statement.IfStatement] node.
        """

    def visit_inline_assembly(self, node: ir.InlineAssembly):
        """
        Visit [InlineAssembly][wake.ir.statements.inline_assembly.InlineAssembly] node.
        """

    def visit_placeholder_statement(self, node: ir.PlaceholderStatement):
        """
        Visit [PlaceholderStatement][wake.ir.statements.placeholder_statement.PlaceholderStatement] node.
        """

    def visit_return(self, node: ir.Return):
        """
        Visit [Return][wake.ir.statements.return_statement.Return] node.
        """

    def visit_revert_statement(self, node: ir.RevertStatement):
        """
        Visit [RevertStatement][wake.ir.statements.revert_statement.RevertStatement] node.
        """

    def visit_try_statement(self, node: ir.TryStatement):
        """
        Visit [TryStatement][wake.ir.statements.try_statement.TryStatement] node.
        """

    def visit_unchecked_block(self, node: ir.UncheckedBlock):
        """
        Visit [UncheckedBlock][wake.ir.statements.unchecked_block.UncheckedBlock] node.
        """

    def visit_variable_declaration_statement(
        self, node: ir.VariableDeclarationStatement
    ):
        """
        Visit [VariableDeclarationStatement][wake.ir.statements.variable_declaration_statement.VariableDeclarationStatement] node.
        """

    def visit_while_statement(self, node: ir.WhileStatement):
        """
        Visit [WhileStatement][wake.ir.statements.while_statement.WhileStatement] node.
        """

    # type names
    def visit_type_name_abc(self, node: ir.TypeNameAbc):
        """
        Visit any [TypeNameAbc][wake.ir.type_names.abc.TypeNameAbc] node.
        """

    def visit_array_type_name(self, node: ir.ArrayTypeName):
        """
        Visit [ArrayTypeName][wake.ir.type_names.array_type_name.ArrayTypeName] node.
        """

    def visit_elementary_type_name(self, node: ir.ElementaryTypeName):
        """
        Visit [ElementaryTypeName][wake.ir.type_names.elementary_type_name.ElementaryTypeName] node.
        """

    def visit_function_type_name(self, node: ir.FunctionTypeName):
        """
        Visit [FunctionTypeName][wake.ir.type_names.function_type_name.FunctionTypeName] node.
        """

    def visit_mapping(self, node: ir.Mapping):
        """
        Visit [Mapping][wake.ir.type_names.mapping.Mapping] node.
        """

    def visit_user_defined_type_name(self, node: ir.UserDefinedTypeName):
        """
        Visit [UserDefinedTypeName][wake.ir.type_names.user_defined_type_name.UserDefinedTypeName] node.
        """

    # yul
    def visit_yul_assignment(self, node: ir.YulAssignment):
        """
        Visit [YulAssignment][wake.ir.yul.assignment.YulAssignment] node.
        """

    def visit_yul_block(self, node: ir.YulBlock):
        """
        Visit [YulBlock][wake.ir.yul.block.YulBlock] node.
        """

    def visit_yul_break(self, node: ir.YulBreak):
        """
        Visit [YulBreak][wake.ir.yul.break_statement.YulBreak] node.
        """

    def visit_yul_case(self, node: ir.YulCase):
        """
        Visit [YulCase][wake.ir.yul.case_.YulCase] node.
        """

    def visit_yul_continue(self, node: ir.YulContinue):
        """
        Visit [YulContinue][wake.ir.yul.continue_statement.YulContinue] node.
        """

    def visit_yul_expression_statement(self, node: ir.YulExpressionStatement):
        """
        Visit [YulExpressionStatement][wake.ir.yul.expression_statement.YulExpressionStatement] node.
        """

    def visit_yul_for_loop(self, node: ir.YulForLoop):
        """
        Visit [YulForLoop][wake.ir.yul.for_loop.YulForLoop] node.
        """

    def visit_yul_function_call(self, node: ir.YulFunctionCall):
        """
        Visit [YulFunctionCall][wake.ir.yul.function_call.YulFunctionCall] node.
        """

    def visit_yul_function_definition(self, node: ir.YulFunctionDefinition):
        """
        Visit [YulFunctionDefinition][wake.ir.yul.function_definition.YulFunctionDefinition] node.
        """

    def visit_yul_identifier(self, node: ir.YulIdentifier):
        """
        Visit [YulIdentifier][wake.ir.yul.identifier.YulIdentifier] node.
        """

    def visit_yul_if(self, node: ir.YulIf):
        """
        Visit [YulIf][wake.ir.yul.if_statement.YulIf] node.
        """

    def visit_yul_leave(self, node: ir.YulLeave):
        """
        Visit [YulLeave][wake.ir.yul.leave.YulLeave] node.
        """

    def visit_yul_literal(self, node: ir.YulLiteral):
        """
        Visit [YulLiteral][wake.ir.yul.literal.YulLiteral] node.
        """

    def visit_yul_switch(self, node: ir.YulSwitch):
        """
        Visit [YulSwitch][wake.ir.yul.switch.YulSwitch] node.
        """

    def visit_yul_typed_name(self, node: ir.YulTypedName):
        """
        Visit [YulTypedName][wake.ir.yul.typed_name.YulTypedName] node.
        """

    def visit_yul_variable_declaration(self, node: ir.YulVariableDeclaration):
        """
        Visit [YulVariableDeclaration][wake.ir.yul.variable_declaration.YulVariableDeclaration] node.
        """

    def generate_link_from_line_col(
        self, path: Union[str, Path], line: int, col: int
    ) -> str:
        """
        Generate a link to the given source unit file location.

        Args:
            path: Path to the source unit file.
            line: Line number.
            col: Column number.

        Returns:
            A link formatted according to the [link_format][wake.config.data_model.GeneralConfig.link_format] configuration option.
        """
        if isinstance(path, Path):
            path = str(path.resolve())
        return self.config.general.link_format.format(path=path, line=line, col=col)

    def generate_link(self, node: ir.IrAbc) -> str:
        """
        Generate a link to the start of the given node based on [name_location][wake.ir.declarations.abc.DeclarationAbc.name_location] or [byte_location][wake.ir.abc.IrAbc.byte_location].

        Args:
            node: Node to generate a link to.

        Returns:
            A link formatted according to the [link_format][wake.config.data_model.GeneralConfig.link_format] configuration option.
        """
        if isinstance(node, ir.DeclarationAbc):
            line, col = node.source_unit.get_line_col_from_byte_offset(
                node.name_location[0]
            )
        else:
            line, col = node.source_unit.get_line_col_from_byte_offset(
                node.byte_location[0]
            )
        return self.generate_link_from_line_col(node.source_unit.file, line, col)
