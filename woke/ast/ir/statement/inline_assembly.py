from typing import Optional

from woke.ast.enums import InlineAssemblyEvmVersion
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcInlineAssembly


class InlineAssembly(StatementAbc):
    _ast_node: SolcInlineAssembly
    _parent: IrAbc  # TODO: make this more specific

    # __ast: TODO
    __evm_version: InlineAssemblyEvmVersion
    # __external_references TODO
    __documentation: Optional[str]

    def __init__(
        self, init: IrInitTuple, inline_assembly: SolcInlineAssembly, parent: IrAbc
    ):
        super().__init__(init, inline_assembly, parent)
        self.__evm_version = inline_assembly.evm_version
        self.__documentation = inline_assembly.documentation

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def evm_version(self) -> InlineAssemblyEvmVersion:
        return self.__evm_version

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
