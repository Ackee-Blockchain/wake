# Debugging

## Using Python debugger

Both commands `woke test` and `woke fuzz` support entering [pdb](https://docs.python.org/3/library/pdb.html), the Python debugger, when an error occurs.
Woke uses an enhanced version of the Python debugger, [pdrb](https://github.com/cansarigol/pdbr), which provides a more user-friendly interface.

It is also possible to enter the debugger manually by inserting a `breakpoint()` statement in the code.

```python
from woke.testing import *

@default_chain.connect()
def test_breakpoint():
    breakpoint()
    block = default_chain.blocks[0]
```

!!! info
    `breakpoint()` is not currently supported with `woke fuzz`.

Inside pdbr, any expression can be evaluated by typing it and pressing `Enter`.
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

```python
from woke.testing import *
from pytypes.contracts.Counter import Counter
from pytypes.contracts.Gateway import Gateway

@default_chain.connect()
def test_call_trace():
    default_chain.set_default_accounts(default_chain.accounts[0])

    gateway = Gateway.deploy()
    counter = Counter.deploy()
    counter.addToWhitelist(gateway)

    tx = gateway.execute(
        counter,
        Abi.encode_call(counter.decrement, []),
        return_tx=True
    )
    print(tx.call_trace)

    tx = gateway.execute(
        counter,
        Abi.encode_call(counter.increment, []),
        return_tx=True
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
from woke.testing import *
from pytypes.contracts.Counter import Counter

@default_chain.connect()
def test_console_logs():
    default_chain.tx_callback = lambda tx: print(tx.console_logs)
    default_chain.set_default_accounts(default_chain.accounts[0])

    counter = Counter.deploy()
    counter.increment()
    counter.setCount(42)
```

!!! tip "Woke-integrated `console.sol`"
    Woke integrates the `console.sol` library implementing the same functionalities as Hardhat's `console.sol`.
    It can serve as a drop-in replacement in case that the tested project is not using Hardhat.

    ```solidity
    import "woke/console.sol";
    
    contract MyContract {
        function myFunction() public view {
            console.log("Hello world!");
        }
    }
    ```

!!! info
    Accessing transaction `console_logs` is not currently supported with Hardhat and Ganache.