import os
import time
from contextlib import contextmanager, nullcontext
from typing import Any, Dict, Iterable, Optional, Union, cast
from urllib.error import HTTPError

import eth_utils
from Crypto.Hash import keccak
from rich.console import Group
from rich.pretty import pprint
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm
from rich.table import Table

import wake.development.core
from wake.cli.console import console
from wake.development.chain_interfaces import AnvilChainInterface, TxParams
from wake.development.core import (
    Abi,
    Address,
    RequestType,
    RevertToSnapshotFailedError,
    TransactionConfirmationFailedError,
    Wei,
    check_connected,
    fix_library_abi,
)
from wake.development.globals import chain_interfaces_manager, get_config
from wake.development.json_rpc.communicator import JsonRpcError
from wake.development.transactions import (
    Eip1559Transaction,
    Eip2930Transaction,
    LegacyTransaction,
    TransactionAbc,
    TransactionStatusEnum,
)
from wake.development.utils import chain_explorer_urls
from wake.utils.formatters import format_wei


class Chain(wake.development.core.Chain):
    @contextmanager
    def connect(
        self,
        uri: Optional[str] = None,
        *,
        accounts: Optional[int] = None,
        chain_id: Optional[int] = None,
        fork: Optional[str] = None,
        hardfork: Optional[str] = None,
        min_gas_price: Optional[Union[int, str]] = None,
        block_base_fee_per_gas: Optional[Union[int, str]] = None,
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
        self._require_signed_txs = True

        if min_gas_price is not None:
            try:
                self._chain_interface.set_min_gas_price(min_gas_price)
            except (JsonRpcError, HTTPError):
                pass

    def _connect_finalize(self) -> None:
        chain_interfaces_manager.close(self._chain_interface)

    def _new_private_key(self, extra_entropy: bytes = b"") -> bytes:
        data = os.urandom(32) + extra_entropy
        return keccak.new(data=data, digest_bits=256).digest()

    @check_connected
    def snapshot(self) -> str:
        snapshot_id = self._chain_interface.snapshot()

        self._snapshots[snapshot_id] = {
            "nonces": self._nonces.copy(),
            "accounts": self._accounts.copy(),
            "default_call_account": self._default_call_account,
            "default_tx_account": self._default_tx_account,
            "txs": dict(self._txs._transactions),
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
        self._txs._transactions = snapshot["txs"]
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

        n = self._nonces[Address(sender)]
        tx: TxParams = {
            "nonce": n,
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
                if (
                    isinstance(self.chain_interface, AnvilChainInterface)
                    or self.require_signed_txs
                ):
                    tx["maxFeePerGas"] = tx["maxPriorityFeePerGas"] + int(
                        int(
                            self.chain_interface.get_block("pending")["baseFeePerGas"],
                            16,
                        )
                        * 2
                    )

        if "gas" not in params or params["gas"] == "auto":
            # use "auto when unset
            try:
                tx_copy = tx.copy()
                tx_copy.pop("gasPrice", None)
                tx_copy.pop("maxPriorityFeePerGas", None)
                tx_copy.pop("maxFeePerGas", None)
                tx["gas"] = int(self._chain_interface.estimate_gas(tx_copy) * 1.1)
            except JsonRpcError as e:
                raise self._process_call_revert(e) from None
        elif isinstance(params["gas"], int):
            tx["gas"] = params["gas"]
        else:
            raise ValueError(f"Invalid gas value: {params['gas']}")

        if (
            tx_type in {1, 2}
            and ("accessList" not in params or params["accessList"] == "auto")
            and request_type != "access_list"
        ):
            try:
                response = self._chain_interface.create_access_list(tx)
                gas_used = int(int(response["gasUsed"], 16) * 1.1)

                if params.get("accessList", None) == "auto" or (
                    "accessList" not in params and gas_used <= tx["gas"]
                ):
                    tx["accessList"] = response["accessList"]

                    if "gas" not in params or params["gas"] == "auto":
                        tx["gas"] = gas_used
            except (JsonRpcError, HTTPError) as e:
                try:
                    if isinstance(e, JsonRpcError):
                        # will re-raise if not a revert error
                        raise self._process_call_revert(e) from None
                    else:
                        # HTTPError -> eth_createAccessList not supported
                        if "accessList" not in params:
                            tx["accessList"] = []
                        else:
                            raise
                except JsonRpcError:
                    # eth_createAccessList probably not supported
                    if "accessList" not in params:
                        tx["accessList"] = []
                    else:
                        raise

        return tx

    def _wait_for_transaction(
        self, tx: TransactionAbc, confirmations: Optional[int]
    ) -> None:
        def get_pending_text():
            if tx.chain.chain_id in chain_explorer_urls:
                text = f"Waiting for transaction [link={chain_explorer_urls[tx.chain.chain_id].url}/tx/{tx.tx_hash}]{tx.tx_hash}[/link] to be mined\n"
            else:
                text = f"Waiting for transaction {tx.tx_hash} to be mined\n"

            t = Table("", "Set in transaction", "Current recommended")

            if isinstance(tx, Eip1559Transaction):
                recommended_priority_fee = (
                    self.chain_interface.get_max_priority_fee_per_gas()
                )
                base_fee = int(
                    self.chain_interface.get_block("pending")["baseFeePerGas"], 16
                )

                t.add_row(
                    "Max fee per gas",
                    format_wei(tx.max_fee_per_gas),
                    format_wei(recommended_priority_fee + base_fee),
                )
                t.add_row(
                    "Max priority fee per gas",
                    format_wei(tx.max_priority_fee_per_gas),
                    format_wei(recommended_priority_fee),
                )
            elif isinstance(tx, (Eip2930Transaction, LegacyTransaction)):
                t.add_row(
                    "Gas price",
                    format_wei(tx.gas_price),
                    format_wei(self.chain_interface.get_gas_price()),
                )

            return Group(text, t)

        if confirmations == 0:
            return
        elif confirmations is None:
            confirmations = self.default_tx_confirmations

        config = get_config()

        ctx_manager = (
            console.status(get_pending_text())
            if not config.deployment.silent
            else nullcontext()
        )

        with ctx_manager as status:
            while tx.status == TransactionStatusEnum.PENDING:
                time.sleep(0.5)
                if status is not None:
                    status.update(get_pending_text())

        if not config.deployment.silent:
            if tx.chain.chain_id in chain_explorer_urls:
                console.print(
                    f"Transaction [link={chain_explorer_urls[tx.chain.chain_id].url}/tx/{tx.tx_hash}]{tx.tx_hash}[/link] mined in block {tx.block_number}"
                )
            else:
                console.print(
                    f"Transaction {tx.tx_hash} mined in block {tx.block_number}"
                )

        latest_block_number = self.chain_interface.get_block_number()

        ctx_manager = (
            Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed} of {task.total}"),
                TimeElapsedColumn(),
                console=console,
            )
            if not config.deployment.silent
            else nullcontext()
        )

        with ctx_manager as progress:
            if progress is not None:
                task_id = progress.add_task(
                    "Confirmations",
                    total=confirmations,
                    completed=(latest_block_number - tx.block_number + 1),
                )
            while latest_block_number - tx.block_number < confirmations - 1:
                time.sleep(1)
                latest_block_number = self.chain_interface.get_block_number()
                if progress is not None:
                    progress.update(
                        task_id,  # pyright: ignore reportUnboundVariable
                        completed=(latest_block_number - tx.block_number + 1),
                    )

    def _confirm_transaction(self, tx: TxParams) -> None:
        config = get_config()
        if config.deployment.silent:
            return
        pprint(tx, console=console, max_string=200)

        if config.deployment.confirm_transactions:
            confirm = Confirm.ask("Sign and send transaction?")
            if not confirm:
                raise TransactionConfirmationFailedError()


default_chain = Chain()
