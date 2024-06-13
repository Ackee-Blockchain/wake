from __future__ import annotations

from functools import wraps
from typing import Any, ContextManager, Dict, List, NamedTuple, Optional

from wake.development.transactions import TransactionRevertedError
from wake.lsp.context import LspContext
from wake.lsp.exceptions import LspError
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.protocol_structures import ErrorCodes
from wake.testing import Account, Chain


class CompilationResult(LspModel):
    success: bool
    contracts: Dict[str, List]  # fqn -> ABI


class DeployResult(LspModel):
    success: bool
    contract_address: Optional[str]
    tx_receipt: Dict[str, Any]
    # call_trace: str

class CallResult(LspModel):
    success: bool
    return_value: bytes
    tx_receipt: Dict[str, Any]
    # call_trace: str


class ContractInfo(NamedTuple):
    abi: List
    bytecode: str


class SakeDeployParams(LspModel):
    contract_fqn: str
    sender: str
    calldata: str
    value: int


class SakeCallParams(LspModel):
    contract_address: str
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
        success, bytecode_result = await self.lsp_context.compiler.bytecode_compile()

        if success:
            self.compilation = {
                fqn: ContractInfo(
                    abi=info.abi,
                    bytecode=info.bytecode,
                )
                for fqn, info in bytecode_result.items()
            }

        _contracts = {fqn: info.abi for fqn, info in self.compilation.items()}

        return CompilationResult(success=success, contracts=_contracts)

    @launch_chain
    async def get_accounts(self) -> List[str]:
        assert self.chain is not None

        return [str(a.address) for a in self.chain.accounts]

    @launch_chain
    async def deploy(self, params: SakeDeployParams) -> DeployResult:
        assert self.chain is not None

        try:
            bytecode = self.compilation[params.contract_fqn].bytecode
        except KeyError:
            raise LspError(
                ErrorCodes.InvalidParams, f"Contract {params.contract_fqn} not compiled"
            )

        try:
            tx = self.chain.deploy(
                bytes.fromhex(bytecode + params.calldata),
                from_=params.sender,
                value=params.value,
                return_tx=True,
            )
            assert tx._tx_receipt is not None
            return DeployResult(
                success=True,
                contract_address=str(tx.return_value.address),
                tx_receipt=tx._tx_receipt,
                # call_trace=str(tx.call_trace),
            )
        except TransactionRevertedError as e:
            assert e.tx is not None
            assert e.tx._tx_receipt is not None
            return DeployResult(
                success=False,
                contract_address=None,
                tx_receipt=e.tx._tx_receipt,
                # call_trace=str(e.tx.call_trace),
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @launch_chain
    async def call(self, params: SakeCallParams) -> CallResult:
        assert self.chain is not None

        try:
            tx = Account(params.contract_address, self.chain).transact(
                data=bytes.fromhex(params.calldata),
                value=params.value,
                from_=params.sender,
            )
            assert tx._tx_receipt is not None
            assert isinstance(tx.raw_return_value, bytearray)
            return CallResult(
                success=True,
                return_value=tx.raw_return_value,
                tx_receipt=tx._tx_receipt,
                # call_trace=str(tx.call_trace),
            )
        except TransactionRevertedError as e:
            assert e.tx is not None
            assert e.tx._tx_receipt is not None
            assert e.tx.raw_error is not None
            return CallResult(
                success=False,
                return_value=e.tx.raw_error.data,
                tx_receipt=e.tx._tx_receipt,
                # call_trace=str(e.tx.call_trace),
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None
