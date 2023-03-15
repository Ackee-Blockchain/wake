# Deployment

<div id="deployment-asciinema" style="z-index: 1; position: relative;"></div>
<script>
  window.onload = function(){
    AsciinemaPlayer.create('../deployment.cast', document.getElementById('deployment-asciinema'), { preload: true, autoPlay: true, rows: 15 });
}
</script>

## Differences from testing

Most information about testing is applicable to deployment as well. However, there are a few key differences.
The behavior depends on whether `woke.testing` or `woke.deployment` is imported.

`woke.deployment` should be used when interacting with a live chain (testnet or mainnet). `woke.testing` should be used when interacting with a local development chain (like Anvil, Ganache, or Hardhat).

```python
# use woke.deployment when interacting with a live chain
from woke.deployment import *

# use woke.testing when interacting with a local development chain
from woke.testing import *
```

### `chain.connect` keyword arguments

The context manager `chain.connect` takes `min_gas_price` and `block_base_fee_per_gas` keyword arguments.
In testing, these are set to `0` by default. In deployment, these are set to `None` by default.

### Required signed transactions

In testing, transactions are not required to be signed for performance reasons. In deployment, transactions are required to be signed by default.
That is, `chain.require_signed_transactions` is `True` by default.

### `chain.block_gas_limit`

In testing, the value of `chain.block_gas_limit` is cached for performance reasons. In deployment, the value is always fetched from the chain for the current `pending` block.

### `chain.gas_price`

`chain.gas_price` is a constant value in testing and can be modified by the user. In deployment, `chain.gas_price` is a value returned by the `eth_gasPrice` JSON-RPC method.

### `chain.max_priority_fee_per_gas`

`chain.max_priority_fee_per_gas` is a constant value in testing and can be modified by the user. In deployment, `chain.max_priority_fee_per_gas` is a value returned by the `eth_maxPriorityFeePerGas` JSON-RPC method.

## Managing accounts with private keys

While it is possible to import accounts from a private key or mnemonic phrase at runtime, it is not recommended.
To protect your private keys, it should be encrypted and stored in a file. To do this, use `woke accounts` CLI commands.

```console
$ woke accounts --help
                                                                           
 Usage: woke accounts [OPTIONS] COMMAND [ARGS]...                          
                                                                           
 Run Woke accounts manager.                                                
                                                                           
╭─ Options ───────────────────────────────────────────────────────────────╮
│ --help      Show this message and exit.                                 │
╰─────────────────────────────────────────────────────────────────────────╯
╭─ Commands ──────────────────────────────────────────────────────────────╮
│ export    Export an account's private key.                              │
│ import    Import an account from a private key or mnemonic.             │
│ list      List all accounts.                                            │
│ new       Create a new account.                                         │
│ remove    Remove an account.                                            │
╰─────────────────────────────────────────────────────────────────────────╯
```

Accounts are referenced by their alias, which is a unique identifier, string, defined by the user. Accounts can be imported by their alias in scripts:

```python
a = Account.from_alias("my-account")
```

## Writing deployment scripts

`woke.deployment` module can be imported in test files. This can be useful when both interacting with a live chain and [pytest](https://docs.pytest.org/en/stable/) features like fixtures are needed.
This way, integration tests can be written using the same conventions as unit tests.

To distinguish between tests and deployment scripts, it is possible to execute Python scripts using the `woke run` CLI command.
The Python scripts must define a `main` function, which will be executed when the script is run.

When no arguments are passed to `woke run`, the `scripts` directory is searched for Python scripts.

```python title="scripts/deploy.py"
from woke.deployment import *
from pytypes.contracts.Counter import Counter

ALCHEMY_API_KEY = "YOUR_ALCHEMY_API_KEY"

@default_chain.connect(f"wss://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")
def main():
    acc = Account.from_alias("deployment")
    default_chain.set_default_accounts(acc)

    counter = Counter.deploy()
    print(counter)

    counter.increment()
    assert counter.count() == 1
```

And then run the script:

```shell
woke run scripts/deploy.py
```
