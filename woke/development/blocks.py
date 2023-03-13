from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Union

from typing_extensions import Literal

if TYPE_CHECKING:
    from .core import Account, Chain, Wei
    from .transactions import TransactionAbc


class ChainBlocks:
    _chain: Chain
    _blocks: Dict[int, Block]

    def __init__(self, chain: Chain):
        self._chain = chain
        self._blocks = {}

    def __getitem__(
        self,
        key: Union[
            int,
            Literal["latest"],
            Literal["pending"],
            Literal["earliest"],
            Literal["safe"],
            Literal["finalized"],
        ],
    ) -> Block:
        if isinstance(key, int) and key < 0:
            key = self._chain.chain_interface.get_block_number() + key + 1
        if key not in self._blocks:
            data = self._chain.chain_interface.get_block(key)
            if data is None:
                raise KeyError(key)

            block = Block(self._chain, data)

            if "number" in data and data["number"] is not None:
                block_number = int(data["number"], 16)
                if block_number in self._blocks:
                    return self._blocks[block_number]

                if block.number <= self._chain.chain_interface.get_block_number():
                    self._blocks[block.number] = block
        else:
            block = self._blocks[key]
        return block

    def __len__(self):
        return self["latest"].number - self["earliest"].number + 1

    def __iter__(self) -> Iterator[Block]:
        for i in range(self["earliest"].number, self["latest"].number + 1):
            yield self[i]


class Block:
    _chain: Chain
    _block_data: Dict[str, Any]

    def __init__(self, chain: Chain, block_data: Dict[str, Any]):
        self._chain = chain
        self._block_data = block_data

    @property
    def chain(self) -> Chain:
        return self._chain

    @property
    def hash(self) -> str:
        return self._block_data["hash"]

    @property
    def parent_hash(self) -> str:
        return self._block_data["parentHash"]

    @property
    def sha3_uncles(self) -> str:
        return self._block_data["sha3Uncles"]

    @property
    def miner(self) -> Account:
        from .core import Account

        return Account(self._block_data["miner"], self._chain)

    @property
    def state_root(self) -> str:
        return self._block_data["stateRoot"]

    @property
    def transactions_root(self) -> str:
        return self._block_data["transactionsRoot"]

    @property
    def receipts_root(self) -> str:
        return self._block_data["receiptsRoot"]

    @property
    def number(self) -> int:
        return int(self._block_data["number"], 16)

    @property
    def gas_used(self) -> int:
        return int(self._block_data["gasUsed"], 16)

    @property
    def gas_limit(self) -> int:
        return int(self._block_data["gasLimit"], 16)

    @property
    def logs_bloom(self) -> str:
        return self._block_data["logsBloom"]

    @property
    def timestamp(self) -> int:
        return int(self._block_data["timestamp"], 16)

    @property
    def difficulty(self) -> int:
        return int(self._block_data["difficulty"], 16)

    @property
    def total_difficulty(self) -> int:
        return int(self._block_data["totalDifficulty"], 16)

    @property
    def seal_fields(self) -> Optional[List[str]]:
        if (
            "sealFields" in self._block_data
            and self._block_data["sealFields"] is not None
        ):
            return list(self._block_data["sealFields"])
        return None

    @property
    def uncles(self) -> List[str]:
        return list(self._block_data["uncles"])

    @property
    def txs(self) -> List[TransactionAbc]:
        return [self._chain.txs[tx] for tx in self._block_data["transactions"]]

    @property
    def size(self) -> int:
        return int(self._block_data["size"], 16)

    @property
    def mix_hash(self) -> str:
        return self._block_data["mixHash"]

    @property
    def nonce(self) -> str:
        return self._block_data["nonce"]

    @property
    def extra_data(self) -> str:
        return self._block_data["extraData"]

    @property
    def base_fee_per_gas(self) -> Optional[Wei]:
        if (
            "baseFeePerGas" in self._block_data
            and self._block_data["baseFeePerGas"] is not None
        ):
            from .core import Wei

            return Wei(int(self._block_data["baseFeePerGas"], 16))
        return None
