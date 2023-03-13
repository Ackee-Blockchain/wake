import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional, cast

import eth_utils

import woke.development.core
from woke.development.core import (
    Abi,
    Account,
    Address,
    RequestType,
    RevertToSnapshotFailedError,
    Wei,
    check_connected,
    fix_library_abi,
)
from woke.development.json_rpc.communicator import JsonRpcError, TxParams
from woke.development.transactions import TransactionAbc, TransactionStatusEnum


class Chain(woke.development.core.Chain):
    @contextmanager
    def connect(
        self,
        uri: Optional[str] = None,
        *,
        accounts: Optional[int] = None,
        chain_id: Optional[int] = None,
        fork: Optional[str] = None,
        hardfork: Optional[str] = None,
        min_gas_price: Optional[int] = None,
        block_base_fee_per_gas: Optional[int] = None,
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

    def _connect_setup(self, min_gas_price: Optional[int]) -> None:
        self._require_signed_txs = True

        if min_gas_price is not None:
            try:
                self._chain_interface.set_min_gas_price(min_gas_price)
            except JsonRpcError:
                pass

    def _connect_finalize(self) -> None:
        pass

    def _update_nonce(self, address: Address, nonce: int) -> None:
        # nothing to do
        pass

    @check_connected
    def snapshot(self) -> str:
        snapshot_id = self._chain_interface.snapshot()

        self._snapshots[snapshot_id] = {
            "accounts": self._accounts.copy(),
            "default_call_account": self._default_call_account,
            "default_tx_account": self._default_tx_account,
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
        self._accounts = snapshot["accounts"]
        self._default_call_account = snapshot["default_call_account"]
        self._default_tx_account = snapshot["default_tx_account"]
        self._txs = snapshot["txs"]
        self._blocks._blocks = snapshot["blocks"]
        del self._snapshots[snapshot_id]

    @property
    @check_connected
    def block_gas_limit(self) -> int:
        return self._blocks["pending"].gas_limit

    @block_gas_limit.setter
    @check_connected
    def block_gas_limit(self, value: int) -> None:
        raise NotImplementedError(
            "Cannot set block gas limit in deployment"
        )  # TODO do nothing instead?

    @property
    @check_connected
    def gas_price(self) -> Wei:
        return Wei(self.chain_interface.get_gas_price())

    @gas_price.setter
    @check_connected
    def gas_price(self, value: int) -> None:
        raise NotImplementedError(
            "Cannot set gas price in deployment"
        )  # TODO do nothing instead?

    @property
    @check_connected
    def max_priority_fee_per_gas(self) -> Wei:
        return Wei(self.chain_interface.get_max_priority_fee_per_gas())

    @max_priority_fee_per_gas.setter
    @check_connected
    def max_priority_fee_per_gas(self, value: int) -> None:
        raise NotImplementedError(
            "Cannot set max priority fee per gas in deployment"
        )  # TODO do nothing instead?

    def _build_transaction(
        self,
        request_type: RequestType,
        params: TxParams,
        arguments: Iterable,
        abi: Optional[Dict],
    ) -> TxParams:
        tx_type = params.get("type", self._tx_type)
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
            "nonce": Account(sender, self).nonce,
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
                params["gasPrice"] if "gasPrice" in params else self.gas_price
            )
        elif tx_type == 1:
            tx["chainId"] = self._chain_id
            tx["gasPrice"] = (
                params["gasPrice"] if "gasPrice" in params else self.gas_price
            )
        elif tx_type == 2:
            tx["chainId"] = self._chain_id
            tx["maxPriorityFeePerGas"] = (
                params["maxPriorityFeePerGas"]
                if "maxPriorityFeePerGas" in params
                else self.max_priority_fee_per_gas
            )
            if "maxFeePerGas" in params:
                tx["maxFeePerGas"] = params["maxFeePerGas"]
            else:
                if self.require_signed_txs:
                    tx["maxFeePerGas"] = tx["maxPriorityFeePerGas"] + int(
                        self.chain_interface.get_block("pending")["baseFeePerGas"], 16
                    )

        if "gas" not in params or params["gas"] == "auto":
            # use "auto when unset
            try:
                tx["gas"] = self._chain_interface.estimate_gas(tx)
            except JsonRpcError as e:
                self._process_call_revert(e)
                raise
        elif isinstance(params["gas"], int):
            tx["gas"] = params["gas"]
        else:
            raise ValueError(f"Invalid gas value: {params['gas']}")

        if tx_type in {1, 2} and (
            "accessList" not in params or params["accessList"] == "auto"
        ):
            try:
                response = self._chain_interface.create_access_list(tx)
                tx["accessList"] = response["accessList"]

                if "gas" not in params or params["gas"] == "auto":
                    tx["gas"] = int(response["gasUsed"], 16)
            except JsonRpcError as e:
                self._process_call_revert(e)
                raise

        return tx

    def _wait_for_transaction(
        self, tx: TransactionAbc, confirmations: Optional[int]
    ) -> None:
        if confirmations == 0:
            return
        elif confirmations is None:
            confirmations = 5

        while tx.status == TransactionStatusEnum.PENDING:
            time.sleep(0.25)

        while self.blocks["latest"].number - tx.block.number < confirmations - 1:
            time.sleep(0.25)


default_chain = Chain()
