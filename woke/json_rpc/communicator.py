import logging

import aiohttp
from aiohttp import ClientSession

from .data_model import *

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class JsonRpcCommunicator:
    __client_session: Optional[ClientSession]
    __port: Optional[int]
    __request_id: int
    __url: str

    def __init__(
        self,
        url: str = "http://localhost",
        port: Optional[int] = None,
        client_session: Optional[ClientSession] = None,
    ):
        self.__client_session = client_session
        self.__port = port
        self.__request_id = 0
        if port is None:
            self.__url = url
        else:
            self.__url = f"{url}:{port}"

    async def __send_request(
        self, method_name: str, params: Optional[List] = None
    ) -> str:
        request_data = JsonRpcRequest(
            method=method_name,
            params=(params if params is not None else []),
            id=self.__request_id,
        )
        post_data = request_data.dict()
        logger.info(f"Sending request:\n{post_data}")
        self.__request_id += 1

        if self.__client_session is not None:
            async with self.__client_session.post(
                self.__url, json=post_data
            ) as response:
                text = await response.text()
                logger.info(f"Received response:\n{text}")
                return text
        else:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.__url, json=post_data) as response:
                    text = await response.text()
                    logger.info(f"Received response:\n{text}")
                    return text

    async def eth_block_number(self) -> int:
        """Returns the number of most recent block."""
        text = await self.__send_request("eth_blockNumber")
        response = JsonRpcResponseEthBlockNumber.parse_raw(text)
        return response.result

    async def eth_get_block_by_number(
        self, block_number: Union[int, str], full_transactions: bool
    ) -> JsonRpcBlock:
        """Returns information about a block by number."""
        text = await self.__send_request(
            "eth_getBlockByNumber",
            [
                hex(block_number) if type(block_number) is int else block_number,
                full_transactions,
            ],
        )
        response = JsonRpcReponseEthGetBlock.parse_raw(text)
        return response.result

    async def eth_get_transaction_receipt(self, transaction_hash: str):
        """Returns the receipt of a transaction by transaction hash."""
        text = await self.__send_request(
            "eth_getTransactionReceipt", [transaction_hash]
        )
        response = JsonRpcResponseEthGetTransactionReceipt.parse_raw(text)
        return response.result

    async def eth_get_code(self, address: str, block_number: Union[int, str]) -> str:
        """Returns code at a given address."""
        text = await self.__send_request(
            "eth_getCode",
            [
                address,
                hex(block_number) if isinstance(block_number, int) else block_number,
            ],
        )
        response = JsonRpcResponseEthGetCode.parse_raw(text)
        return response.result

    async def eth_get_storage_at(
        self, address: str, storage_slot: int, block_number: Union[int, str]
    ):
        """Returns the value from a storage position at a given address."""
        text = await self.__send_request(
            "eth_getStorageAt",
            [
                address,
                hex(storage_slot),
                hex(block_number) if isinstance(block_number, int) else block_number,
            ],
        )
        response = JsonRpcResponseEthGetStorageAt.parse_raw(text)
        return response.result

    async def debug_trace_transaction(
        self,
        trans_hash: str,
        disable_storage: bool = False,
        disable_memory: bool = False,
        disable_stack: bool = False,
        tracer: str = "",
        timeout: int = 5,
    ) -> JsonRpcTransactionTrace:
        """Returns the transaction trace object for a given transaction-"""
        text = await self.__send_request(
            "debug_traceTransaction",
            [
                trans_hash,
                disable_storage,
                disable_memory,
                disable_stack,
                tracer,
                timeout,
            ],
        )

        response = JsonRpcResponseDebugTraceTransaction.parse_raw(text)
        return response.result
