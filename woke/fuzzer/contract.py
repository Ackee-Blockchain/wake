from typing import Any, Iterable, Optional, Type

import eth_abi
import web3.contract
from eth_typing import HexStr
from web3 import Web3
from web3._utils.abi import get_abi_output_types
from web3.types import TxParams


class Contract:
    abi: Any
    bytecode: HexStr
    _w3: Web3
    _contract: web3.contract.Contract

    def __init__(self, w3: Web3, contract: web3.contract.Contract):
        self._w3 = w3
        self._contract = contract

    @classmethod
    def deploy(
        cls, w3: Web3, params: Optional[TxParams] = None
    ) -> web3.contract.Contract:
        factory = w3.eth.contract(abi=cls.abi, bytecode=cls.bytecode)
        tx_hash = factory.constructor().transact(params)
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        return cls(w3, w3.eth.contract(address=tx_receipt["contractAddress"], abi=cls.abi))  # type: ignore

    def transact(self, selector: HexStr, arguments: Iterable, params: TxParams) -> Any:
        func = self._contract.get_function_by_selector(selector)(*arguments)
        output_abi = get_abi_output_types(func.abi)
        # priorities:
        # 1. anvil_enableTraces
        # 2. trace_transaction
        # 3. call
        # 4. debug_traceTransaction

        tx_hash = func.transact(params)
        output = self._w3.eth.trace_transaction(HexStr(tx_hash.hex()))[0].result.output[2:]  # type: ignore
        return eth_abi.abi.decode(output_abi, bytes.fromhex(output))  # type: ignore
