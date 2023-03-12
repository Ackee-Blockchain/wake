from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

import eth_utils

import woke.development.core
from woke.development.core import (
    Abi,
    Address,
    RequestType,
    RevertToSnapshotFailedError,
    check_connected,
    fix_library_abi,
)
from woke.development.json_rpc import JsonRpcError, TxParams

from ..utils.keyed_default_dict import KeyedDefaultDict


class Chain(woke.development.core.Chain):
    _block_gas_limit: int
    _gas_price: int
    _max_priority_fee_per_gas: int
    _nonces: KeyedDefaultDict[Address, int]  # pyright: reportGeneralTypeIssues=false

    def _connect_setup(self) -> None:
        connected_chains.append(self)

        self._require_signed_txs = False
        self._gas_price = 0
        self._max_priority_fee_per_gas = 0
        self._nonces = KeyedDefaultDict(
            lambda addr: self._chain_interface.get_transaction_count(
                str(addr)
            )  # pyright: reportGeneralTypeIssues=false
        )
        block_info = self._chain_interface.get_block("pending")
        assert "gasLimit" in block_info
        self._block_gas_limit = int(block_info["gasLimit"], 16)

    def _connect_finalize(self) -> None:
        connected_chains.remove(self)

    def _update_nonce(self, address: Address, nonce: int) -> None:
        self._nonces[address] = nonce

    @check_connected
    def snapshot(self) -> str:
        snapshot_id = self._chain_interface.snapshot()

        self._snapshots[snapshot_id] = {
            "nonces": self._nonces.copy(),
            "accounts": self._accounts.copy(),
            "default_call_account": self._default_call_account,
            "default_tx_account": self._default_tx_account,
            "block_gas_limit": self._block_gas_limit,
            "txs": dict(self._txs),
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
        self._txs = snapshot["txs"]
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
    def gas_price(self) -> int:
        return self._gas_price

    @gas_price.setter
    @check_connected
    def gas_price(self, value: int) -> None:
        self._gas_price = value

    @property
    @check_connected
    def max_priority_fee_per_gas(self) -> int:
        return self._max_priority_fee_per_gas

    @max_priority_fee_per_gas.setter
    @check_connected
    def max_priority_fee_per_gas(self, value: int) -> None:
        self._max_priority_fee_per_gas = value

    def _build_transaction(
        self,
        request_type: RequestType,
        params: TxParams,
        arguments: Iterable,
        abi: Optional[Dict],
    ) -> TxParams:
        if "gasPrice" in params and (
            "maxFeePerGas" in params or "maxPriorityFeePerGas" in params
        ):
            raise ValueError(
                "Cannot specify both gas_price and max_fee_per_gas/max_priority_fee_per_gas"
            )
        if "maxFeePerGas" in params or "maxPriorityFeePerGas" in params:
            tx_type = 2
        elif "accessList" in params:
            tx_type = 1
        elif "gasPrice" in params:
            tx_type = 0
        else:
            tx_type = self._tx_type

        if "from" in params:
            sender = params["from"]
        else:
            if request_type == "call" and self.default_call_account is not None:
                sender = str(self.default_call_account.address)
            elif request_type == "tx" and self.default_tx_account is not None:
                sender = str(self.default_tx_account.address)
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
            "nonce": self._nonces[sender],
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
            tx["accessList"] = params["accessList"] if "accessList" in params else []
            tx["chainId"] = self._chain_id
            tx["gasPrice"] = (
                params["gasPrice"] if "gasPrice" in params else self._gas_price
            )
        elif tx_type == 2:
            tx["accessList"] = params["accessList"] if "accessList" in params else []
            tx["chainId"] = self._chain_id
            tx["maxPriorityFeePerGas"] = (
                params["maxPriorityFeePerGas"]
                if "maxPriorityFeePerGas" in params
                else self._max_priority_fee_per_gas
            )
            if "maxFeePerGas" in params:
                tx["maxFeePerGas"] = params["maxFeePerGas"]
            else:
                if self.require_signed_txs:
                    tx["maxFeePerGas"] = tx["maxPriorityFeePerGas"] + int(
                        self.chain_interface.get_block("pending")["baseFeePerGas"], 16
                    )

        if "gas" not in params:
            # use "max" when unset
            tx["gas"] = self._block_gas_limit
        elif isinstance(params["gas"], int):
            tx["gas"] = params["gas"]
        elif params["gas"] == "auto":
            # auto
            try:
                tx["gas"] = self._chain_interface.estimate_gas(tx)
            except JsonRpcError as e:
                self._process_call_revert(e)
                raise
        else:
            raise ValueError(f"Invalid gas value: {params['gas']}")

        return tx


default_chain = Chain()
connected_chains: List[Chain] = []


def get_connected_chains() -> Tuple[Chain, ...]:
    return tuple(connected_chains)
