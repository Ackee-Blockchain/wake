from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union, cast

import eth_utils
from Crypto.Hash import keccak

import wake.development.core
from wake.development.chain_interfaces import TxParams
from wake.development.core import (
    Abi,
    Account,
    Address,
    RequestType,
    RevertToSnapshotFailedError,
    Wei,
    check_connected,
    fix_library_abi,
)
from wake.development.globals import chain_interfaces_manager, random
from wake.development.json_rpc import JsonRpcError

from ..development.chain_interfaces import AnvilChainInterface
from ..development.transactions import TransactionAbc, TransactionStatusEnum


class Chain(wake.development.core.Chain):
    _block_gas_limit: int
    _gas_price: Wei
    _max_priority_fee_per_gas: Wei
    _initial_base_fee_per_gas: Wei

    @contextmanager
    def connect(
        self,
        uri: Optional[str] = None,
        *,
        accounts: Optional[int] = None,
        chain_id: Optional[int] = None,
        fork: Optional[str] = None,
        hardfork: Optional[str] = None,
        min_gas_price: Optional[Union[int, str]] = 0,
        block_base_fee_per_gas: Optional[Union[int, str]] = 0,
    ):
        yield from self._connect(
            uri,
            accounts=accounts,
            chain_id=chain_id,
            fork=fork,
            hardfork=hardfork,
            min_gas_price=min_gas_price,
            block_base_fee_per_gas=block_base_fee_per_gas,
        )

    def _connect_setup(
        self, min_gas_price: Optional[int], block_base_fee_per_gas: Optional[int]
    ) -> None:
        connected_chains.append(self)

        self._require_signed_txs = False
        self._gas_price = Wei(0)
        self._max_priority_fee_per_gas = Wei(0)
        block_info = self._chain_interface.get_block("pending")
        assert "gasLimit" in block_info
        self._block_gas_limit = int(block_info["gasLimit"], 16)

        if block_base_fee_per_gas is not None:
            self._initial_base_fee_per_gas = Wei(block_base_fee_per_gas)
        else:
            self._initial_base_fee_per_gas = block_info.get("baseFeePerGas", 0)

        if min_gas_price is not None:
            try:
                self._chain_interface.set_min_gas_price(min_gas_price)
                self.gas_price = min_gas_price
            except JsonRpcError:
                pass
        else:
            self.gas_price = self._chain_interface.get_gas_price()

    def _connect_finalize(self) -> None:
        connected_chains.remove(self)
        chain_interfaces_manager.free(self._chain_interface)

    def _new_private_key(self, extra_entropy: bytes = b"") -> bytes:
        data = random.getrandbits(256).to_bytes(32, "little") + extra_entropy
        return keccak.new(data=data, digest_bits=256).digest()

    @check_connected
    def snapshot(self) -> str:
        snapshot_id = self._chain_interface.snapshot()

        self._snapshots[snapshot_id] = {
            "nonces": self._nonces.copy(),
            "accounts": self._accounts.copy(),
            "default_call_account": self._default_call_account,
            "default_tx_account": self._default_tx_account,
            "block_gas_limit": self._block_gas_limit,
            "txs": dict(self._txs._transactions),
            "tx_hashes": list(self._txs._tx_hashes),
            "blocks": dict(self._blocks._blocks),
        }
        return snapshot_id

    @check_connected
    def revert(self, snapshot_id: str) -> None:
        reverted = self._chain_interface.revert(snapshot_id)
        if not reverted:
            raise RevertToSnapshotFailedError()

        snapshot = self._snapshots[snapshot_id]
        self._nonces = snapshot["nonces"]
        self._accounts = snapshot["accounts"]
        self._default_call_account = snapshot["default_call_account"]
        self._default_tx_account = snapshot["default_tx_account"]
        self._block_gas_limit = snapshot["block_gas_limit"]
        self._txs._transactions = snapshot["txs"]
        self._txs._tx_hashes = snapshot["tx_hashes"]
        self._blocks._blocks = snapshot["blocks"]
        del self._snapshots[snapshot_id]

    @property
    @check_connected
    def block_gas_limit(self) -> int:
        return self._block_gas_limit

    @block_gas_limit.setter
    @check_connected
    def block_gas_limit(self, value: int) -> None:
        self._chain_interface.set_block_gas_limit(value)
        self._block_gas_limit = value

    @property
    @check_connected
    def gas_price(self) -> Wei:
        return self._gas_price

    @gas_price.setter
    @check_connected
    def gas_price(self, value: int) -> None:
        self._gas_price = Wei(value)

    @property
    @check_connected
    def max_priority_fee_per_gas(self) -> Wei:
        return self._max_priority_fee_per_gas

    @max_priority_fee_per_gas.setter
    @check_connected
    def max_priority_fee_per_gas(self, value: int) -> None:
        self._max_priority_fee_per_gas = Wei(value)

    def _build_transaction(
        self,
        request_type: RequestType,
        params: TxParams,
        arguments: Iterable,
        abi: Optional[Dict],
    ) -> TxParams:
        tx_type = params.get("type", self._default_tx_type)
        if tx_type not in {0, 1, 2}:
            raise ValueError("Invalid transaction type")

        if tx_type == 0 and (
            "accessList" in params
            or "maxFeePerGas" in params
            or "maxPriorityFeePerGas" in params
        ):
            raise ValueError(
                "Cannot specify accessList, maxFeePerGas, or maxPriorityFeePerGas for type 0 transaction"
            )
        elif tx_type == 1 and (
            "maxFeePerGas" in params or "maxPriorityFeePerGas" in params
        ):
            raise ValueError(
                "Cannot specify maxFeePerGas or maxPriorityFeePerGas for type 1 transaction"
            )
        elif tx_type == 2 and "gasPrice" in params:
            raise ValueError("Cannot specify gasPrice for type 2 transaction")

        if "from" in params:
            sender = params["from"]
        else:
            if request_type == "call" and self.default_call_account is not None:
                sender = str(self.default_call_account.address)
            elif request_type == "tx" and self.default_tx_account is not None:
                sender = str(self.default_tx_account.address)
            elif (
                request_type == "estimate" and self.default_estimate_account is not None
            ):
                sender = str(self.default_estimate_account.address)
            elif (
                request_type == "access_list"
                and self.default_access_list_account is not None
            ):
                sender = str(self.default_access_list_account.address)
            else:
                raise ValueError(
                    "No from_ account specified and no default account set"
                )

        if "data" not in params:
            params["data"] = b""

        if abi is None:
            params["data"] += Abi.encode([], [])
        else:
            arguments = [self._convert_to_web3_type(arg) for arg in arguments]
            types = [
                eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                for arg in fix_library_abi(abi["inputs"])
            ]
            params["data"] += Abi.encode(types, arguments)

        tx: TxParams = {
            "nonce": self._nonces[Address(sender)],
            "from": sender,
            "value": params["value"] if "value" in params else 0,
            "data": params["data"],
        }
        if tx_type != 0:
            tx["type"] = tx_type

        if "to" in params:
            tx["to"] = params["to"]

        if tx_type == 0:
            tx["gasPrice"] = (
                params["gasPrice"] if "gasPrice" in params else self._gas_price
            )
        elif tx_type == 1:
            if "accessList" not in params:
                tx["accessList"] = []
            elif params["accessList"] != "auto":
                tx["accessList"] = params["accessList"]
            tx["chainId"] = self._chain_id
            tx["gasPrice"] = (
                params["gasPrice"] if "gasPrice" in params else self._gas_price
            )
        elif tx_type == 2:
            if "accessList" not in params:
                tx["accessList"] = []
            elif params["accessList"] != "auto":
                tx["accessList"] = params["accessList"]
            tx["chainId"] = self._chain_id
            tx["maxPriorityFeePerGas"] = (
                params["maxPriorityFeePerGas"]
                if "maxPriorityFeePerGas" in params
                else self._max_priority_fee_per_gas
            )
            if "maxFeePerGas" in params:
                tx["maxFeePerGas"] = params["maxFeePerGas"]
            else:
                if isinstance(self.chain_interface, AnvilChainInterface) or (
                    self.require_signed_txs
                    and Account(tx["from"], self) not in self._accounts_set
                ):
                    # not really correct (base fee may/will change in time)
                    # temporary workaround until Anvil implements https://github.com/foundry-rs/foundry/issues/4360
                    tx["maxFeePerGas"] = (
                        tx["maxPriorityFeePerGas"] + self._initial_base_fee_per_gas
                    )

        if "gas" not in params:
            # use "max" when unset
            tx["gas"] = self._block_gas_limit
        elif isinstance(params["gas"], int):
            tx["gas"] = params["gas"]
        elif params["gas"] == "auto":
            # auto
            try:
                tx["gas"] = int(self._chain_interface.estimate_gas(tx) * 1.1)
            except JsonRpcError as e:
                raise self._process_call_revert(e) from None
        else:
            raise ValueError(f"Invalid gas value: {params['gas']}")

        if (
            tx_type in {1, 2}
            and "accessList" in params
            and params["accessList"] == "auto"
        ):
            try:
                response = self._chain_interface.create_access_list(tx)
                tx["accessList"] = response["accessList"]

                if "gas" in params and params["gas"] == "auto":
                    tx["gas"] = int(response["gasUsed"], 16)
            except JsonRpcError as e:
                raise self._process_call_revert(e) from None

        return tx

    def _wait_for_transaction(
        self, tx: TransactionAbc, confirmations: Optional[int]
    ) -> None:
        if confirmations == 0:
            return
        elif confirmations is None:
            confirmations = self.default_tx_confirmations

        while tx.status == TransactionStatusEnum.PENDING:
            pass

        if confirmations == 1:
            return

        while self.blocks["latest"].number - tx.block_number < confirmations - 1:
            pass

    def _confirm_transaction(self, tx: TxParams) -> None:
        pass


default_chain = Chain()
connected_chains: List[Chain] = []


def get_connected_chains() -> Tuple[Chain, ...]:
    return tuple(connected_chains)
