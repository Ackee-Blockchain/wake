from __future__ import annotations

import json
import re
from collections import ChainMap, defaultdict
from dataclasses import dataclass
from functools import wraps
from typing import Any, ContextManager, Dict, List, NamedTuple, Optional, Tuple, Union

import eth_utils
from Crypto.Hash import BLAKE2b, keccak
from typing_extensions import Literal

import wake.development.core
from wake.config import WakeConfig
from wake.development.call_trace import CallTrace
from wake.development.chain_interfaces import AnvilChainInterface
from wake.development.core import Library, RequestType, get_fqn_from_address
from wake.development.globals import set_config
from wake.development.json_rpc import JsonRpcError
from wake.development.transactions import TransactionStatusEnum
from wake.development.utils import (
    AbiNotFound,
    get_logic_contract,
    get_name_abi_from_explorer,
)
from wake.lsp.context import LspContext
from wake.lsp.exceptions import LspError
from wake.lsp.lsp_data_model import LspModel
from wake.lsp.protocol_structures import ErrorCodes
from wake.testing import Account, Address, Chain, UnknownTransactionRevertedError
from wake.utils.file_utils import is_relative_to


class SakeResult(LspModel):
    success: bool


class SakeParams(LspModel):
    session_id: str


class ErrorInfo(LspModel):
    message: str
    path: str
    start_offset: int
    end_offset: int


class SkippedInfo(LspModel):
    message: str
    path: str


class SakeCompilationResult(SakeResult):
    contracts: Dict[str, ContractInfoLsp]  # fqn -> ABI
    errors: Dict[str, List[ErrorInfo]]
    skipped: Dict[str, SkippedInfo]


# @dev used for api to include name in json, otherwise tuple is converted to array
class ContractInfoLsp(LspModel):
    abi: List
    is_deployable: bool


class SakeCreateChainParams(LspModel):
    session_id: str
    chain_id: Optional[int]
    accounts: Optional[int]
    fork: Optional[str]
    hardfork: Optional[str]
    min_gas_price: Optional[int]
    block_base_fee_per_gas: Optional[int]


class SakeCreateChainResult(SakeResult):
    accounts: List[str]
    uri: Optional[str]
    type: str


class SakeConnectChainParams(LspModel):
    session_id: str
    uri: str


class SakeDeployParams(SakeParams):
    contract_fqn: str
    sender: str
    calldata: str
    value: int


class SakeDeployResult(SakeResult):
    contract_address: Optional[str]
    raw_error: Optional[str]  # raw hex encoded bytes, None for Success or Halt
    error: Optional[str]  # user-friendly error string, None for Success
    events: List[
        str
    ]  # user-friendly event strings, in correct order, excluding events from reverting subtraces
    tx_receipt: Dict[str, Any]
    call_trace: Dict[str, Union[Optional[str], List]]


class SakeCallParams(SakeParams):
    contract_address: str
    sender: str
    calldata: str
    value: int


class SakeCallResult(SakeResult):
    return_value: str
    call_trace: Optional[Dict[str, Union[Optional[str], List]]]


class SakeTransactParams(SakeCallParams):
    pass


class SakeTransactResult(SakeResult):
    return_value: Optional[str]  # raw hex encoded bytes, None for Halt
    error: Optional[str]  # user-friendly error string, None for Success
    events: List[
        str
    ]  # user-friendly event strings, in correct order, excluding events from reverting subtraces
    tx_receipt: Dict[str, Any]
    call_trace: Dict[str, Union[Optional[str], List]]


class SakeGetBalancesParams(SakeParams):
    addresses: List[str]


class SakeGetBalancesResult(SakeResult):
    balances: Dict[str, int]


class SakeSetBalancesParams(SakeParams):
    balances: Dict[str, int]


class SakeSetBalancesResult(SakeResult):
    pass


class SakeSetLabelParams(SakeParams):
    address: str
    label: Optional[str]


class SakeStateMetadata(LspModel):
    labels: Dict[str, str]
    deployed_libraries: Dict[str, List[str]]


class SakeDumpStateResult(SakeResult):
    metadata: SakeStateMetadata
    chain_dump: str


class SakeLoadStateParams(SakeParams):
    metadata: SakeStateMetadata
    chain_dump: str


class SakeGetAbiParams(SakeParams):
    address: str
    chain_id: int


class SakeGetAbiResult(SakeResult):
    name: str
    abi: List


class SakeGetAbiWithProxyParams(SakeParams):
    address: str


class SakeGetAbiWithProxyResult(SakeResult):
    name: str
    abi: List
    proxy_name: Optional[str]
    proxy_abi: Optional[List]
    implementation_address: Optional[str]


class WorkspaceState(LspModel):
    info_by_fqn: Dict[str, ContractInfo]
    libraries: Dict[str, str]
    creation_code_index: List[Tuple[Tuple[Tuple[int, str], ...], str]]
    fqn_by_metadata: Dict[str, str]


class SakeLoadWorkspaceStateParams(SakeParams):
    state: WorkspaceState


class SakeSaveWorkspaceStateResult(SakeResult):
    state: WorkspaceState


@dataclass
class ContractInfo:
    name: str
    abi: Dict[Union[bytes, Literal["constructor", "fallback", "receive"]], List]


def chain_connected(f):
    @wraps(f)
    async def wrapper(context: SakeContext, params: SakeParams, *args, **kwargs):
        if (
            params.session_id not in context.chains
            or not context.chains[params.session_id][0].connected
        ):
            raise LspError(ErrorCodes.InvalidParams, "Chain instance not connected")

        return await f(context, params, *args, **kwargs)

    return wrapper


LIBRARY_PLACEHOLDER_REGEX = re.compile(r"__\$[0-9a-fA-F]{34}\$__")


class SakeContext:
    lsp_context: LspContext
    chains: Dict[str, Tuple[Chain, ContextManager]]
    bytecode_by_fqn: Dict[str, str]
    info_by_fqn: Dict[str, ContractInfo]
    libraries: Dict[bytes, str]  # lib_id -> fqn
    creation_code_index: List[Tuple[Tuple[Tuple[int, bytes], ...], str]]
    fqn_by_metadata: Dict[bytes, str]

    def __init__(self, lsp_context: LspContext):
        self.lsp_context = lsp_context
        self.chains = {}
        self.bytecode_by_fqn = {}  # NOT saved in dump
        self.info_by_fqn = {}  # saved in dump
        self.libraries = {}  # saved in dump
        self.creation_code_index = []  # saved in dump
        self.fqn_by_metadata = {}  # saved in dump

    async def ping(self) -> SakeResult:
        return SakeResult(success=True)

    async def load_workspace_state(
        self, params: SakeLoadWorkspaceStateParams
    ) -> SakeResult:
        try:
            self.info_by_fqn = params.state.info_by_fqn
            self.libraries = {
                bytes.fromhex(lib_id): fqn
                for lib_id, fqn in params.state.libraries.items()
            }
            self.creation_code_index = [
                (tuple((length, bytes.fromhex(h)) for length, h in segments), fqn)
                for segments, fqn in params.state.creation_code_index
            ]
            self.fqn_by_metadata = {
                bytes.fromhex(metadata): fqn
                for metadata, fqn in params.state.fqn_by_metadata.items()
            }
            return SakeResult(success=True)
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    async def save_workspace_state(self) -> SakeSaveWorkspaceStateResult:
        try:
            return SakeSaveWorkspaceStateResult(
                success=True,
                state=WorkspaceState(
                    info_by_fqn=self.info_by_fqn,
                    libraries={
                        lib_id.hex(): fqn for lib_id, fqn in self.libraries.items()
                    },
                    creation_code_index=[
                        (tuple((length, h.hex()) for length, h in segments), fqn)
                        for segments, fqn in self.creation_code_index
                    ],
                    fqn_by_metadata={
                        metadata.hex(): fqn
                        for metadata, fqn in self.fqn_by_metadata.items()
                    },
                ),
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    async def create_chain(
        self, params: SakeCreateChainParams
    ) -> SakeCreateChainResult:
        try:
            config_clone = WakeConfig.fromdict(
                self.lsp_context.config.todict(),
                project_root_path=self.lsp_context.config.project_root_path,
            )
            # reset Anvil args & always use Anvil
            config_clone.update(
                {},
                deleted_options=[("testing", "cmd"), ("testing", "anvil", "cmd_args")],
            )
            set_config(config_clone)
            chain = Chain()
            chain_handle = chain.connect(
                accounts=params.accounts,
                chain_id=params.chain_id,
                fork=params.fork,
                hardfork=params.hardfork,
                min_gas_price=params.min_gas_price,
                block_base_fee_per_gas=params.block_base_fee_per_gas,
            )
            chain_handle.__enter__()

            self.chains[params.session_id] = (chain, chain_handle)

            return SakeCreateChainResult(
                success=True,
                accounts=[str(a.address) for a in chain.accounts],
                uri=chain.chain_interface.connection_uri,
                type=chain.chain_interface.type,
            )
        except FileNotFoundError:
            raise LspError(ErrorCodes.AnvilNotFound, "Anvil executable not found")
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    async def connect_chain(
        self, params: SakeConnectChainParams
    ) -> SakeCreateChainResult:
        try:
            config_clone = WakeConfig.fromdict(
                self.lsp_context.config.todict(),
                project_root_path=self.lsp_context.config.project_root_path,
            )
            # reset Anvil args & always use Anvil
            config_clone.update(
                {},
                deleted_options=[("testing", "cmd"), ("testing", "anvil", "cmd_args")],
            )
            set_config(config_clone)
            chain = Chain()
            chain_handle = chain.connect(params.uri)
            chain_handle.__enter__()

            self.chains[params.session_id] = (chain, chain_handle)

            return SakeCreateChainResult(
                success=True,
                accounts=[str(a.address) for a in chain.accounts],
                uri=chain.chain_interface.connection_uri,
                type=chain.chain_interface.type,
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def disconnect_chain(self, params: SakeParams) -> SakeResult:
        try:
            self.chains[params.session_id][1].__exit__(None, None, None)
            del self.chains[params.session_id]
            return SakeResult(success=True)
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def dump_state(self, params: SakeParams) -> SakeDumpStateResult:
        chain = self.chains[params.session_id][0]

        if not isinstance(chain.chain_interface, AnvilChainInterface):
            raise LspError(
                ErrorCodes.InvalidRequest,
                "Chain state dump is only supported for Anvil",
            )

        try:
            return SakeDumpStateResult(
                success=True,
                metadata=SakeStateMetadata(
                    labels={str(a): label for a, label in chain._labels.items()},
                    deployed_libraries={
                        id.hex(): [str(lib.address) for lib in libs]
                        for id, libs in chain._deployed_libraries.items()
                    },
                ),
                chain_dump=chain.chain_interface.dump_state(),
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def load_state(self, params: SakeLoadStateParams) -> SakeResult:
        chain = self.chains[params.session_id][0]

        if not isinstance(chain.chain_interface, AnvilChainInterface):
            raise LspError(
                ErrorCodes.InvalidRequest,
                "Chain state load is only supported for Anvil",
            )

        try:
            chain.chain_interface.load_state(params.chain_dump)

            chain._labels = {
                Address(addr): label for addr, label in params.metadata.labels.items()
            }
            chain._deployed_libraries = defaultdict(list)
            for id, addrs in params.metadata.deployed_libraries.items():
                chain._deployed_libraries[bytes.fromhex(id)] = [
                    wake.development.core.Library(Address(addr), chain)
                    for addr in addrs
                ]
            return SakeResult(success=True)
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    async def compile(self) -> SakeCompilationResult:
        try:
            (
                success,
                contract_info,
                asts,
                errors,
                skipped_source_units,
                source_units_to_paths,
            ) = await self.lsp_context.compiler.bytecode_compile()

            self.libraries.clear()
            bytecode_by_fqn = {}

            for fqn, info in contract_info.items():
                if (
                    info.evm is None
                    or info.evm.bytecode is None
                    or info.evm.bytecode.object is None
                    or info.evm.deployed_bytecode is None
                    or info.evm.deployed_bytecode.object is None
                ):
                    continue

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

                if contract_node["contractKind"] == "library":
                    lib_id = keccak.new(
                        data=fqn.encode("utf-8"), digest_bits=256
                    ).digest()[:17]
                    self.libraries[lib_id] = fqn

                assert info.abi is not None
                abi_by_selector = {}
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
                        abi_by_selector[selector] = item
                    elif item["type"] == "error":
                        selector = eth_utils.abi.function_abi_to_4byte_selector(item)
                        abi_by_selector[selector] = item
                    elif item["type"] == "event":
                        selector = eth_utils.abi.event_abi_to_log_topic(item)
                        abi_by_selector[selector] = item
                    elif item["type"] in {"constructor", "fallback", "receive"}:
                        abi_by_selector[item["type"]] = item
                    else:
                        raise ValueError(f"Unknown ABI item type: {item['type']}")

                self.info_by_fqn[fqn] = ContractInfo(
                    name=contract_node["name"], abi=abi_by_selector
                )

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

                    self.creation_code_index.append((tuple(bytecode_segments), fqn))

                config = next(
                    (
                        config
                        for config in self.lsp_context.config.subproject.values()
                        if any(
                            is_relative_to(source_units_to_paths[source_unit_name], p)
                            for p in config.paths
                        )
                    ),
                    self.lsp_context.config.compiler.solc,
                )

                if (
                    len(info.evm.deployed_bytecode.object) > 0
                    and config.metadata.append_CBOR != False
                    and config.metadata.bytecode_hash != "none"
                ):
                    metadata_length = int.from_bytes(
                        bytes.fromhex(info.evm.deployed_bytecode.object[-4:]),
                        "big",
                    )
                    metadata = bytes.fromhex(
                        info.evm.deployed_bytecode.object[-metadata_length * 2 - 4 : -4]
                    )
                    self.fqn_by_metadata[metadata] = fqn

                bytecode_by_fqn[fqn] = bytecode

            wake.development.core.creation_code_index = self.creation_code_index
            wake.development.core.contracts_by_metadata = self.fqn_by_metadata

            if success:
                self.bytecode_by_fqn = bytecode_by_fqn

            return SakeCompilationResult(
                success=success,
                contracts={
                    fqn: ContractInfoLsp(
                        abi=list(self.info_by_fqn[fqn].abi.values()),
                        is_deployable=(len(bytecode) > 0),
                    )
                    for fqn, bytecode in self.bytecode_by_fqn.items()
                },
                errors={
                    source_unit_name: [
                        ErrorInfo(
                            message=error[0],
                            path=str(error[1]),
                            start_offset=error[2],
                            end_offset=error[3],
                        )
                        for error in e
                    ]
                    for source_unit_name, e in errors.items()
                },
                skipped={
                    source_unit_name: SkippedInfo(
                        message=skipped[0], path=str(skipped[1])
                    )
                    for source_unit_name, skipped in skipped_source_units.items()
                },
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def get_accounts(self, params: SakeParams) -> List[str]:
        return [str(a.address) for a in self.chains[params.session_id][0].accounts]

    @chain_connected
    async def deploy(self, params: SakeDeployParams) -> SakeDeployResult:
        chain = self.chains[params.session_id][0]

        def fqn_to_contract_abi(fqn: str):
            return None, self.info_by_fqn[fqn].abi

        try:
            bytecode = self.bytecode_by_fqn[params.contract_fqn]

            for match in LIBRARY_PLACEHOLDER_REGEX.finditer(bytecode):
                lib_id = bytes.fromhex(match.group(0)[3:-3])
                assert lib_id in self.libraries

                if lib_id in chain._deployed_libraries:
                    lib_addr = str(chain._deployed_libraries[lib_id][-1].address)[2:]
                else:
                    raise LspError(
                        ErrorCodes.RequestFailed,
                        f"Library {self.libraries[lib_id].split(':')[1]} must be deployed first",
                    )

                bytecode = (
                    bytecode[: match.start()] + lib_addr + bytecode[match.end() :]
                )
        except KeyError:
            raise LspError(
                ErrorCodes.InvalidParams, f"Contract {params.contract_fqn} not compiled"
            )

        try:
            tx = chain.deploy(
                bytes.fromhex(bytecode + params.calldata),
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
                chain,
                tx.to,
                tx.return_value if success else None,
                ChainMap(),
                tx.block_number - 1,
                self.info_by_fqn.keys(),
                fqn_to_contract_abi,
            )

            assert tx._tx_receipt is not None

            if success:
                lib_id = keccak.new(
                    data=params.contract_fqn.encode("utf-8"), digest_bits=256
                ).digest()[:17]
                if lib_id in self.libraries:
                    chain._deployed_libraries[lib_id].append(
                        Library(tx.return_value, chain)
                    )

            return SakeDeployResult(
                success=success,
                error=call_trace.error_string,
                events=call_trace.event_strings,
                raw_error=(
                    tx.raw_error.data.hex()
                    if isinstance(tx.raw_error, UnknownTransactionRevertedError)
                    else None
                ),
                contract_address=str(tx.return_value.address) if success else None,
                tx_receipt=tx._tx_receipt,
                call_trace=call_trace.dict(self.lsp_context.config),
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def transact(self, params: SakeTransactParams) -> SakeTransactResult:
        chain = self.chains[params.session_id][0]

        def fqn_to_contract_abi(fqn: str):
            return None, self.info_by_fqn[fqn].abi

        try:
            tx = Account(params.contract_address, chain).transact(
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
                chain,
                tx.to,
                None,
                ChainMap(),
                tx.block_number - 1,
                self.info_by_fqn.keys(),
                fqn_to_contract_abi,
            )

            assert tx._tx_receipt is not None

            if success:
                assert isinstance(tx.raw_return_value, bytearray)
                return_value = tx.raw_return_value.hex()
            else:
                assert tx.raw_error is not None
                return_value = (
                    tx.raw_error.data.hex()
                    if isinstance(tx.raw_error, UnknownTransactionRevertedError)
                    else None
                )

            return SakeTransactResult(
                success=success,
                error=call_trace.error_string,
                events=call_trace.event_strings,
                return_value=return_value,
                tx_receipt=tx._tx_receipt,
                call_trace=call_trace.dict(self.lsp_context.config),
            )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def call(self, params: SakeCallParams) -> SakeCallResult:
        chain = self.chains[params.session_id][0]

        def fqn_to_contract_abi(fqn: str):
            return None, self.info_by_fqn[fqn].abi

        try:
            account = Account(params.contract_address, chain=chain)
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
            tx_params = chain._build_transaction(RequestType.CALL, tx_params, [], None)

            trace = chain.chain_interface.debug_trace_call(
                tx_params, options={"enableMemory": True}
            )
            ret_value = trace["returnValue"]
            call_trace = CallTrace.from_debug_trace(
                trace,
                tx_params,
                chain,
                account,
                None,
                ChainMap(),
                chain.blocks["latest"].number,
                self.info_by_fqn.keys(),
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
                ret_value = chain.chain_interface.call(
                    tx_params  # pyright: ignore reportPossiblyUnboundVariable
                )
                return SakeCallResult(
                    success=True,
                    return_value=ret_value.hex(),
                    call_trace=None,
                )
            except JsonRpcError as e:
                try:
                    revert_data = chain._process_call_revert_data(e)
                    return SakeCallResult(
                        success=False,
                        return_value=revert_data.hex(),
                        call_trace=None,
                    )
                except Exception:
                    raise LspError(ErrorCodes.InternalError, str(e)) from None
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def get_balances(
        self, params: SakeGetBalancesParams
    ) -> SakeGetBalancesResult:
        chain = self.chains[params.session_id][0]

        try:
            balances = {
                address: chain.chain_interface.get_balance(address)
                for address in params.addresses
            }

            return SakeGetBalancesResult(success=True, balances=balances)
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def set_balances(
        self, params: SakeSetBalancesParams
    ) -> SakeSetBalancesResult:
        chain = self.chains[params.session_id][0]

        try:
            for address, balance in params.balances.items():
                chain.chain_interface.set_balance(address, balance)

            return SakeSetBalancesResult(success=True)
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def set_label(self, params: SakeSetLabelParams) -> SakeResult:
        chain = self.chains[params.session_id][0]

        try:
            Account(params.address, chain=chain).label = params.label
            return SakeResult(success=True)
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    async def get_abi(self, params: SakeGetAbiParams) -> SakeGetAbiResult:
        try:
            try:
                name, abi = get_name_abi_from_explorer(params.address, params.chain_id)
                return SakeGetAbiResult(success=True, name=name, abi=list(abi.values()))
            except AbiNotFound as e:
                if e.api_key_name is not None:
                    raise LspError(
                        ErrorCodes.AbiNotFound,
                        f"ABI not found for {params.address}",
                        {
                            "apiKeyName": e.api_key_name,
                            "tomlUsed": self.lsp_context.use_toml
                            and self.lsp_context.toml_path.is_file(),
                            "configPath": str(
                                self.lsp_context.config.global_config_path
                            ),
                        },
                    )
                else:
                    raise LspError(
                        ErrorCodes.AbiNotFound,
                        f"ABI not found for {params.address}",
                        {},
                    )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    @chain_connected
    async def get_abi_with_proxy(
        self, params: SakeGetAbiWithProxyParams
    ) -> SakeGetAbiWithProxyResult:
        def info_from_address(address: str) -> Tuple[str, List]:
            fqn = get_fqn_from_address(logic_contract.address, "latest", chain)
            if fqn is not None:
                name = self.info_by_fqn[fqn].name
                abi = list(self.info_by_fqn[fqn].abi.values())
            elif chain._forked_chain_id is not None:
                try:
                    name, abi = get_name_abi_from_explorer(
                        address, chain._forked_chain_id
                    )
                    abi = list(abi.values())
                except AbiNotFound as e:
                    if e.api_key_name is not None:
                        raise LspError(
                            ErrorCodes.AbiNotFound,
                            f"ABI not found for {address}",
                            {
                                "apiKeyName": e.api_key_name,
                                "tomlUsed": self.lsp_context.use_toml
                                and self.lsp_context.toml_path.is_file(),
                                "configPath": str(
                                    self.lsp_context.config.global_config_path
                                ),
                            },
                        )
                    else:
                        raise LspError(
                            ErrorCodes.AbiNotFound,
                            f"ABI not found for {address}",
                            {},
                        )
            else:
                raise LspError(
                    ErrorCodes.AbiNotFound,
                    f"ABI not found for {address}",
                    {},
                )

            return name, abi

        chain = self.chains[params.session_id][0]

        try:
            contract = Account(params.address, chain=chain)
            logic_contract = get_logic_contract(contract)
            name, abi = info_from_address(str(logic_contract.address))

            if contract == logic_contract:
                return SakeGetAbiWithProxyResult(
                    success=True,
                    name=name,
                    abi=abi,
                    proxy_name=None,
                    proxy_abi=None,
                    implementation_address=None,
                )
            else:
                proxy_name, proxy_abi = info_from_address(params.address)

                return SakeGetAbiWithProxyResult(
                    success=True,
                    name=name,
                    abi=abi,
                    proxy_name=proxy_name,
                    proxy_abi=proxy_abi,
                    implementation_address=str(logic_contract.address),
                )
        except Exception as e:
            raise LspError(ErrorCodes.InternalError, str(e)) from None

    # @chain_connected
    # async def register_abi(self, params: SakeRegisterAbiParams) -> SakeResult:
