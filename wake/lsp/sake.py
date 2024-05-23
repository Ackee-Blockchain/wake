from functools import wraps
from typing import Any, ContextManager, Dict, List, NamedTuple, Optional

from wake.development.transactions import TransactionRevertedError
from wake.lsp.context import LspContext
from wake.lsp.exceptions import LspError
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.protocol_structures import ErrorCodes
from wake.testing import Chain


class CompilationResult(LspModel):
    success: bool
    contracts: Dict[str, List]  # fqn -> ABI


class ContractInfo(NamedTuple):
    abi: List
    bytecode: bytes


class SakeDeployParams(LspModel):
    contract_fqn: str
    sender: str
    calldata: str
    value: int


def launch_chain(f):
    @wraps(f)
    async def wrapper(context: SakeContext, *args, **kwargs):
        if context.chain is None:
            context.chain = Chain()
            context.chain_handle = context.chain.connect()
            context.chain_handle.__enter__()
        return await f(context, *args, **kwargs)

    return wrapper


class SakeContext:
    lsp_context: LspContext
    chain: Optional[Chain]
    chain_handle: Optional[ContextManager]
    compilation: Dict[str, ContractInfo]

    def __init__(self, lsp_context: LspContext):
        self.lsp_context = lsp_context
        self.chain = None
        self.chain_handle = None
        self.compilation = {}

    async def compile(self) -> CompilationResult:
        success, abi = await self.lsp_context.compiler.bytecode_compile()

        return CompilationResult(success=success, contracts=abi)

    @launch_chain
    async def get_accounts(self) -> List[str]:
        assert self.chain is not None

        return [str(a.address) for a in self.chain.accounts]

    @launch_chain
    async def deploy(self, params: SakeDeployParams) -> Dict[str, Any]:
        assert self.chain is not None

        try:
            bytecode = self.compilation[params.contract_fqn].bytecode
        except KeyError:
            raise LspError(
                ErrorCodes.InvalidParams, f"Contract {params.contract_fqn} not compiled"
            )

        try:
            tx = self.chain.deploy(
                bytecode + bytes.fromhex(params.calldata),
                from_=params.sender,
                value=params.value,
                return_tx=True,
            )
            assert tx._tx_receipt is not None
            return tx._tx_receipt
        except TransactionRevertedError as e:
            assert e.tx is not None
            assert e.tx._tx_receipt is not None
            return e.tx._tx_receipt
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None
