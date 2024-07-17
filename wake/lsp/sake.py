from __future__ import annotations

import re
from collections import ChainMap
from functools import wraps
from typing import Any, ContextManager, Dict, List, NamedTuple, Optional, Tuple, Union

import eth_utils
from Crypto.Hash import BLAKE2b, keccak
from typing_extensions import Literal

import wake.development.core
from wake.development.call_trace import CallTrace
from wake.development.core import RequestType
from wake.development.json_rpc import JsonRpcError
from wake.development.transactions import TransactionStatusEnum
from wake.lsp.context import LspContext
from wake.lsp.exceptions import LspError
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.protocol_structures import ErrorCodes
from wake.testing import Account, Chain


class SakeResult(LspModel):
    success: bool


class SakeCompilationResult(SakeResult):
    contracts: Dict[str, ContractInfoLsp]  # fqn -> ABI
    errors: Dict[str, List[str]]


class ContractInfo(NamedTuple):
    abi: List
    bytecode: bytes


# @dev used for api to include name in json, otherwise tuple is converted to array
class ContractInfoLsp(LspModel):
    abi: List
    is_deployable: bool


class SakeDeployParams(LspModel):
    contract_fqn: str
    sender: str
    calldata: str
    value: int


class SakeDeployResult(SakeResult):
    contract_address: Optional[str]
    tx_receipt: Dict[str, Any]
    call_trace: Dict[str, Union[Optional[str], List]]


class SakeTransactParams(LspModel):
    contract_address: str
    sender: str
    calldata: str
    value: int


class SakeTransactResult(SakeResult):
    return_value: str
    tx_receipt: Dict[str, Any]
    call_trace: Dict[str, Union[Optional[str], List]]


class SakeCallParams(LspModel):
    contract_address: str
    sender: str
    calldata: str
    value: int


class SakeCallResult(SakeResult):
    return_value: str
    call_trace: Optional[Dict[str, Union[Optional[str], List]]]


class SakeGetBalancesParams(LspModel):
    addresses: List[str]


class SakeGetBalancesResult(SakeResult):
    balances: Dict[str, int]


class SakeSetBalancesParams(LspModel):
    balances: Dict[str, int]


class SakeSetBalancesResult(SakeResult):
    pass


class SakeSetLabelParams(LspModel):
    address: str
    label: Optional[str]


def launch_chain(f):
    @wraps(f)
    async def wrapper(context: SakeContext, *args, **kwargs):
        if context.chain is None:
            context.chain = Chain()
            context.chain_handle = context.chain.connect()
            context.chain_handle.__enter__()
        return await f(context, *args, **kwargs)

    return wrapper


LIBRARY_PLACEHOLDER_REGEX = re.compile(r"__\$[0-9a-fA-F]{34}\$__")


class SakeContext:
    lsp_context: LspContext
    chain: Optional[Chain]
    chain_handle: Optional[ContextManager]
    compilation: Dict[str, ContractInfo]
    abi_by_fqn: Dict[
        str, Dict[Union[bytes, Literal["constructor", "fallback", "receive"]], List]
    ]  # fqn -> ABI

    def __init__(self, lsp_context: LspContext):
        self.lsp_context = lsp_context
        self.chain = None
        self.chain_handle = None
        self.compilation = {}
        self.abi_by_fqn = {}

    async def compile(self) -> SakeCompilationResult:
        try:
            (
                success,
                contract_info,
                asts,
                errors,
            ) = await self.lsp_context.compiler.bytecode_compile()

            self.abi_by_fqn.clear()
            fqn_by_metadata: Dict[bytes, str] = {}
            creation_code_index: List[Tuple[Tuple[Tuple[int, bytes], ...], str]] = []
            _compilation = {}

            for fqn, info in contract_info.items():
                source_unit_name = fqn.split(":")[0]
                try:
                    ast = asts[source_unit_name]
                    contract_node = next(
                        n
                        for n in ast["nodes"]
                        if n["nodeType"] == "ContractDefinition"
                        and n["name"] == fqn.split(":")[1]
                    )
                except (StopIteration, KeyError):
                    continue

                assert info.abi is not None
                self.abi_by_fqn[fqn] = {}
                for item in info.abi:
                    if item["type"] == "function":
                        if contract_node["contractKind"] == "library":
                            for arg in item["inputs"]:
                                if arg["internalType"].startswith("contract "):
                                    arg["internalType"] = arg["internalType"][9:]
                                elif arg["internalType"].startswith("struct "):
                                    arg["internalType"] = arg["internalType"][7:]
                                elif arg["internalType"].startswith("enum "):
                                    arg["internalType"] = arg["internalType"][5:]

                            selector = keccak.new(
                                data=f"{item['name']}({','.join(arg['internalType'] for arg in item['inputs'])})".encode(
                                    "utf-8"
                                ),
                                digest_bits=256,
                            ).digest()[:4]
                        else:
                            selector = eth_utils.abi.function_abi_to_4byte_selector(
                                item
                            )
                        self.abi_by_fqn[fqn][selector] = item
                    elif item["type"] == "error":
                        selector = eth_utils.abi.function_abi_to_4byte_selector(item)
                        self.abi_by_fqn[fqn][selector] = item
                    elif item["type"] == "event":
                        selector = eth_utils.abi.event_abi_to_log_topic(item)
                        self.abi_by_fqn[fqn][selector] = item
                    elif item["type"] in {"constructor", "fallback", "receive"}:
                        self.abi_by_fqn[fqn][item["type"]] = item
                    else:
                        raise ValueError(f"Unknown ABI item type: {item['type']}")

                assert info.evm is not None
                assert info.evm.bytecode is not None
                assert info.evm.bytecode.object is not None
                bytecode = info.evm.bytecode.object
                if len(bytecode) > 0:
                    bytecode_segments: List[Tuple[int, bytes]] = []
                    start = 0

                    for match in LIBRARY_PLACEHOLDER_REGEX.finditer(bytecode):
                        s = match.start()
                        e = match.end()
                        segment = bytes.fromhex(bytecode[start:s])
                        h = BLAKE2b.new(data=segment, digest_bits=256).digest()
                        bytecode_segments.append((len(segment), h))
                        start = e

                    segment = bytes.fromhex(bytecode[start:])
                    h = BLAKE2b.new(data=segment, digest_bits=256).digest()
                    bytecode_segments.append((len(segment), h))

                    creation_code_index.append((tuple(bytecode_segments), fqn))

                assert info.evm.deployed_bytecode is not None
                assert info.evm.deployed_bytecode.object is not None
                if len(info.evm.deployed_bytecode.object) >= 106:
                    fqn_by_metadata[
                        bytes.fromhex(info.evm.deployed_bytecode.object[-106:])
                    ] = fqn

                _compilation[fqn] = ContractInfo(
                    abi=info.abi,
                    bytecode=bytes.fromhex(bytecode),
                )

            wake.development.core.creation_code_index = creation_code_index
            wake.development.core.contracts_by_metadata = fqn_by_metadata

            if success:
                self.compilation = _compilation

            return SakeCompilationResult(
                success=success,
                contracts={
                    fqn: ContractInfoLsp(abi=info.abi, is_deployable=(len(info.bytecode) > 0))
                    for fqn, info in _compilation.items()
                },
                errors={
                    source_unit_name: list(messages)
                    for source_unit_name, messages in errors.items()
                },
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @launch_chain
    async def get_accounts(self) -> List[str]:
        assert self.chain is not None

        return [str(a.address) for a in self.chain.accounts]

    @launch_chain
    async def deploy(self, params: SakeDeployParams) -> SakeDeployResult:
        assert self.chain is not None

        def fqn_to_contract_abi(fqn: str):
            return None, self.abi_by_fqn[fqn]

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
                confirmations=0,
            )
            tx.wait()
            success = tx.status == TransactionStatusEnum.SUCCESS

            tx._fetch_debug_trace_transaction()  # TODO may not be available
            assert tx._debug_trace_transaction is not None
            call_trace = CallTrace.from_debug_trace(
                tx._debug_trace_transaction,  # pyright: ignore reportArgumentType
                tx._tx_params,
                self.chain,
                tx.to,
                tx.return_value if success else None,
                ChainMap(),
                tx.block_number - 1,
                self.abi_by_fqn.keys(),
                fqn_to_contract_abi,
            )

            assert tx._tx_receipt is not None

            return SakeDeployResult(
                success=success,
                contract_address=str(tx.return_value.address) if success else None,
                tx_receipt=tx._tx_receipt,
                call_trace=call_trace.dict(self.lsp_context.config),
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @launch_chain
    async def transact(self, params: SakeCallParams) -> SakeTransactResult:
        assert self.chain is not None

        def fqn_to_contract_abi(fqn: str):
            return None, self.abi_by_fqn[fqn]

        try:
            tx = Account(params.contract_address, self.chain).transact(
                data=bytes.fromhex(params.calldata),
                value=params.value,
                from_=params.sender,
                confirmations=0,
            )
            tx.wait()
            success = tx.status == TransactionStatusEnum.SUCCESS

            tx._fetch_debug_trace_transaction()  # TODO may not be available
            assert tx._debug_trace_transaction is not None
            call_trace = CallTrace.from_debug_trace(
                tx._debug_trace_transaction,  # pyright: ignore reportArgumentType
                tx._tx_params,
                self.chain,
                tx.to,
                None,
                ChainMap(),
                tx.block_number - 1,
                self.abi_by_fqn.keys(),
                fqn_to_contract_abi,
            )

            assert tx._tx_receipt is not None

            if success:
                assert isinstance(tx.raw_return_value, bytearray)
                return_value = tx.raw_return_value
            else:
                assert tx.raw_error is not None
                return_value = tx.raw_error.data

            return SakeTransactResult(
                success=success,
                return_value=return_value.hex(),
                tx_receipt=tx._tx_receipt,
                call_trace=call_trace.dict(self.lsp_context.config),
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @launch_chain
    async def call(self, params: SakeCallParams) -> SakeCallResult:
        assert self.chain is not None

        def fqn_to_contract_abi(fqn: str):
            return None, self.abi_by_fqn[fqn]

        try:
            account = Account(params.contract_address, chain=self.chain)
            tx_params = account._setup_tx_params(
                RequestType.CALL,
                bytes.fromhex(params.calldata),
                params.value,
                params.sender,
                None,
                None,
                None,
                None,
                None,
                None,
            )
            tx_params = self.chain._build_transaction(
                RequestType.CALL, tx_params, [], None
            )

            trace = self.chain.chain_interface.debug_trace_call(tx_params)
            ret_value = trace["returnValue"]
            call_trace = CallTrace.from_debug_trace(
                trace,
                tx_params,
                self.chain,
                account,
                None,
                ChainMap(),
                self.chain.blocks["latest"].number,
                self.abi_by_fqn.keys(),
                fqn_to_contract_abi,
            )
            return SakeCallResult(
                success=(not trace["failed"]),
                return_value=ret_value[2:] if ret_value.startswith("0x") else ret_value,
                call_trace=call_trace.dict(self.lsp_context.config),
            )
        except JsonRpcError:
            # debug_traceCall not available
            try:
                ret_value = self.chain.chain_interface.call(
                    tx_params  # pyright: ignore reportPossiblyUnboundVariable
                )
                return SakeCallResult(
                    success=True,
                    return_value=ret_value.hex(),
                    call_trace=None,
                )
            except JsonRpcError as e:
                try:
                    revert_data = self.chain._process_call_revert_data(e)
                    return SakeCallResult(
                        success=False,
                        return_value=revert_data.hex(),
                        call_trace=None,
                    )
                except Exception:
                    raise LspError(ErrorCodes.InternalError, str(e)) from None
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @launch_chain
    async def get_balances(
        self, params: SakeGetBalancesParams
    ) -> SakeGetBalancesResult:
        assert self.chain is not None

        try:
            balances = {
                address: self.chain.chain_interface.get_balance(address)
                for address in params.addresses
            }

            return SakeGetBalancesResult(success=True, balances=balances)
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @launch_chain
    async def set_balances(
        self, params: SakeSetBalancesParams
    ) -> SakeSetBalancesResult:
        assert self.chain is not None

        try:
            for address, balance in params.balances.items():
                self.chain.chain_interface.set_balance(address, balance)

            return SakeSetBalancesResult(success=True)
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @launch_chain
    async def set_label(self, params: SakeSetLabelParams) -> None:
        assert self.chain is not None

        try:
            Account(params.address, chain=self.chain).label = params.label
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None
