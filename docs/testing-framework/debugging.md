# Debugging

## Using Python debugger

`wake test` supports entering [pdb](https://docs.python.org/3/library/pdb.html), the Python debugger, when an error occurs.
Wake uses an enhanced version of the Python debugger, [ipdb](https://github.com/gotcha/ipdb), which provides a more user-friendly interface.

It is also possible to enter the debugger manually by inserting a `breakpoint()` statement in the code.

```python
from wake.testing import *


@chain.connect()
def test_breakpoint():
    breakpoint()
    block = chain.blocks[0]
```

!!! info
    `breakpoint()` is not currently supported when running `wake test` in multiprocessing mode (with the `-P` option set)

Inside ipdb, any expression can be evaluated by typing it and pressing `Enter`.
This can be used to get the value of a variable, to call a function, including contract functions, or even to deploy a new contract.

<div id="debugger-asciinema" style="z-index: 1; position: relative;"></div>
<script>
  window.onload = function(){
    AsciinemaPlayer.create('../debugger.cast', document.getElementById('debugger-asciinema'), { preload: true, autoPlay: true, rows: 15 });
}
</script>

Useful commands:

- `h` or `help`: show help
- `c` or `continue`: continue execution
- `n` or `next`: step over the next line
- `l` or `list`: show the current line and a few lines around it
- `q` or `quit`: quit the debugger
- `up` or `down`: move up or down the call stack

## Call traces

Every transaction object has a `call_trace` property that visualizes the call stack of the transaction.
It can be used to debug failing transactions.

!!! tip "External contracts in forking mode"
    When using forking mode (see [`connect` keyword arguments](./chains-and-blocks.md#connect-keyword-arguments)), already present contracts are printed as unknown contracts in call traces.
    To show contract and function names, configure your [API key](../configuration.md#api_keys-namespace) for a given chain explorer.

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter
from pytypes.contracts.Gateway import Gateway


@chain.connect()
def test_call_trace():
    gateway = Gateway.deploy()
    counter = Counter.deploy()
    counter.addToWhitelist(gateway)

    tx = gateway.execute(
        counter,
        Abi.encode_call(counter.decrement, []),
        confirmations=0,
    )
    print(tx.call_trace)

    tx = gateway.execute(
        counter,
        Abi.encode_call(counter.increment, []),
    )
    print(tx.call_trace)
```

<div>
--8<-- "docs/images/testing/call-trace.svg"
</div>

!!! info
    Internal calls are not currently visualized in call traces.


## Console logs

Using the `console.sol` library from [Hardhat](https://hardhat.org/tutorial/debugging-with-hardhat-network#solidity--console.log)
may be the easiest way to debug a contract. Logs can be accessed through the `console_logs` property of a transaction object.
Console logs are available even for failed transactions.

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter


@chain.connect()
def test_console_logs():
    chain.tx_callback = lambda tx: print(tx.console_logs)

    counter = Counter.deploy()
    counter.increment()
    counter.setCount(42)
```

!!! tip "Wake-integrated `console.sol`"
    Wake integrates the `console.sol` library implementing the same functionalities as Hardhat's `console.sol`.
    It can serve as a drop-in replacement in case that the tested project is not using Hardhat.

    ```solidity
    import "wake/console.sol";
    
    contract MyContract {
        function myFunction() public view {
            console.log("Hello world!");
        }
    }
    ```