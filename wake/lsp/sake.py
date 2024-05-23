from typing import Dict, List

from wake.lsp.context import LspContext
from wake.lsp.lsp_data_model import LspModel


class CompilationResult(LspModel):
    success: bool
    contracts: Dict[str, List]  # fqn -> ABI


async def sake_compile(main_context: LspContext) -> CompilationResult:
    success, abi = await main_context.compiler.bytecode_compile()
    return CompilationResult(success=success, contracts=abi)
