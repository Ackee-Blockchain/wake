# Chains and blocks

For single chain tests, Woke provides the global `default_chain` variable. This
variable is a `Chain` object that can be used to change the chain parameters
or access the chain data. Other `Chain` instances can be created, which is
useful in [Cross-chain testing](cross-chain-testing.md).

## Chain properties

The `Chain` object has the following properties:

| Property                            | Description                                                                                                |
|-------------------------------------|------------------------------------------------------------------------------------------------------------|
| `accounts`                          | list of pre-generated `Account` objects                                                                    |
| `automine`                          | whether to automatically mine blocks                                                                       |
| `blocks`                            | property to access the chain blocks                                                                        |
| `block_gas_limit`                   | gas limit for blocks                                                                                       |
| `chain_id`                          | chain ID                                                                                                   |
| `chain_interface`                   | low-level chain interface usefull for debugging and power users                                            |
| `coinbase`                          | coinbase `Account`                                                                                         |
| `connected`                         | whether the chain is connected                                                                             |
| <nobr>`default_call_account`</nobr> | default `Account` used for calls                                                                           |
| <nobr>`default_tx_account`</nobr>   | default `Account` used for transactions                                                                    |
| `gas_price`                         | gas price used for all transactions sent to the chain                                                      |
| `txs`                               | dictionary of transaction objects indexed by transaction hash (a string starting with `0x`)                |
| `tx_callback`                       | callback function to be called when a transaction is mined; applies only to `return_tx=False` transactions |

`automine`, `block_gas_limit`, `coinbase`, `default_call_account`, `default_tx_account`, `gas_price`, and `tx_callback` can be assigned to.

## Chain methods

The `Chain` object has the following methods:

| Method                                         | Description                                                                                |
|------------------------------------------------|--------------------------------------------------------------------------------------------|
| `change_automine`                              | context manager to temporarily change the `automine` property                              |
| `connect`                                      | context manager to launch a chain and connect to it or connect to an already running chain |
| `mine`                                         | mine a block with an optional callback function to set the next block timestamp            |
| `reset`                                        | reset the chain to its initial state                                                       |
| `revert`                                       | revert the chain to a previous state given by a snapshot ID                                |
| `set_min_gas_price`                            | set the minimum gas price accepted by the chain                                            |
| <nobr>`set_next_block_base_fee_per_gas`</nobr> | set the base fee per gas for the next block                                                |
| `snapshot`                                     | take a snapshot of the chain state; return a snapshot ID                                   |
| <nobr>`snapshot_and_revert`</nobr>             | context manager to take a snapshot and revert to it after the context ends                 |
| `update_accounts`                              | update the accounts list                                                                   |

It is recommended to use the context managers `change_automine` and `snapshot_and_revert` instead of setting the `automine` property directly or calling `snapshot` and `revert` manually.

The following example presents the use of `Chain` methods:

```python
from woke.testing import default_chain

def test_chain():
    # launch a chain and connect to it
    with default_chain.connect(), default_chain.snapshot_and_revert():
        # mine a block with the timestamp 1 greater than the previous block
        default_chain.mine(lambda x: x + 1)
```

All `Chain` context managers can be used as decorators:

```python
from woke.testing import default_chain

@default_chain.connect()
@default_chain.snapshot_and_revert()
@default_chain.change_automine(False)
def test_chain():
    # mine a block with the timestamp 1 greater than the previous block
    default_chain.mine(lambda x: x + 1)
```

### `connect` keyword arguments

The `connect` context manager accepts keyword arguments that can override the command line arguments set in [configuration](../configuration.md#testing-namespace) files:

| Keyword argument | Description                    | Default value            |
|------------------|--------------------------------|--------------------------|
| `accounts`       | number of accounts to generate | `None` (do not override) |
| `chain_id`       | chain ID assigned to the chain | `None` (do not override) |
| `fork`           | URL of the chain to fork from  | `None` (do not override) |
| `hardfork`       | hardfork to use                | `None` (do not override) |

!!! warning
    `accounts`, `chain_id`, `fork` and `hardfork` can only be used when launching a new development chain.
    Also, it is not possible to set these keyword arguments when working with Hardhat.

```python
from woke.testing import default_chain

@default_chain.connect(
    accounts=15,
    chain_id=1020,
)
def test_chain():
    assert len(default_chain.accounts) == 15
    assert default_chain.chain_id == 1020
```

## Accessing chain blocks

The `chain.blocks` property can be used to access up-to-date chain blocks data.
It can be indexed by an integer or string literals `latest`, `pending`, `earliest`, `safe`, and `finalized`:

```python
from woke.testing import default_chain
from pytypes.contracts.Counter import Counter

@default_chain.connect()
def test_chain_blocks():
    default_chain.set_default_accounts(default_chain.accounts[0])
    
    # get the block 0
    block0 = default_chain.blocks[0]
    # block 0 and earliest are the same
    assert block0 == default_chain.blocks["earliest"]
    
    counter = Counter.deploy()
    
    # find the first block with non-zero transactions count
    block = next(block for block in default_chain.blocks if len(block.txs) > 0)
    
    assert block.txs[0].return_value == counter

    with default_chain.change_automine(False):
        # block -1 and latest are the same
        assert default_chain.blocks[-1] == default_chain.blocks["latest"]

        tx = counter.increment(return_tx=True)
        
        # pending block contains the transaction
        assert tx in default_chain.blocks["pending"].txs
```

## Block properties

The following table lists the most important block properties:

| Property      | Description                                                          |
|---------------|----------------------------------------------------------------------|
| `chain`       | chain the block belongs to                                           |
| `hash`        | block hash                                                           |
| `number`      | block number                                                         |
| `parent_hash` | parent block hash                                                    |
| `miner`       | miner `Account` of the block                                         |
| `gas_used`    | amount of gas used in the block                                      |
| `gas_limit`   | block gas limit                                                      |
| `timestamp`   | block timestamp                                                      |
| `txs`         | list of transaction objects in the block sorted by transaction index |
