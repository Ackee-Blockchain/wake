# Wake

Wake is a Python-based development and testing framework for Solidity.

Features:

- **Testing framework** - a testing framework for Solidity smart contracts with Python-native equivalents of Solidity types and blazing fast execution.

- **Fuzzer** - a property-based fuzzer for Solidity smart contracts that allows testers to write their fuzz tests in Python.

- **Vulnerability detectors**

- **LSP server**

## Dependencies

- [Python](https://www.python.org/downloads/release/python-3910/) (version 3.7 or higher)
- Rosetta must be enabled on Apple Silicon (M1 & M2) Macs

> :warning: Python 3.12 is experimentally supported.

## Installation

via `pip`

```shell
pip3 install eth-wake
```

## Documentation & Contribution

Wake documentation can be found [here](https://ackeeblockchain.com/wake/docs/latest).

There you can also find a section on [contributing](https://ackeeblockchain.com/wake/docs/latest/contributing/).

## Discovered vulnerabilities

| Vulnerability                                   | Severity | Project | Method           | Discovered by    | Resources                                                                                                                                                                                                              |
|-------------------------------------------------|----------|---------|------------------|------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Profit & loss accounted twice                   | Critical | IPOR    | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Console permanent denial of service             | High     | Brahma  | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-brahma-console-v2-report.pdf)                                                                                      |
| Swap unwinding formula error                    | High     | IPOR    | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Swap unwinding fee accounted twice              | High     | IPOR    | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Incorrect event data                            | High     | Solady  | Integration test | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-solady-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-solady/blob/main/tests/test_erc1155.py) |
| `INTEREST_FROM_STRATEGY_BELOW_ZERO` reverts DoS | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Inaccurate hypothetical interest formula        | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Swap unwinding fee normalization error          | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Missing receive function                        | Medium   | Axelar  | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-axelar-interchain-governance-executor/blob/main/tests/test_fuzz.py)                                                                                             |

## Features

### Testing framework

See [examples](examples) and [documentation](https://ackeeblockchain.com/wake/docs/latest/testing-framework/overview) for more information.

Writing tests is as simple as:

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter

@default_chain.connect()
def test_counter():
    default_chain.set_default_accounts(default_chain.accounts[0])

    counter = Counter.deploy()
    assert counter.count() == 0

    counter.increment()
    assert counter.count() == 1
```

### Fuzzer

Fuzzer builds on top of the testing framework and allows efficient fuzz testing of Solidity smart contracts.

```python
from wake.testing import *
from wake.testing.fuzzing import *
from pytypes.contracts.Counter import Counter

class CounterTest(FuzzTest):
    def pre_sequence(self) -> None:
        self.counter = Counter.deploy()
        self.count = 0

    @flow()
    def increment(self) -> None:
        self.counter.increment()
        self.count += 1

    @flow()
    def decrement(self) -> None:
        with may_revert(Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW)) as e:
            self.counter.decrement()

        if e.value is not None:
            assert self.count == 0
        else:
            self.count -= 1

    @invariant(period=10)
    def count(self) -> None:
        assert self.counter.count() == self.count

@default_chain.connect()
def test_counter():
    default_chain.set_default_accounts(default_chain.accounts[0])
    CounterTest().run(sequences_count=30, flows_count=100)
```

### Vulnerability detectors

Vulnerability detectors can be run using:
```shell
wake detect
```

### LSP server

Wake implements an [LSP](https://microsoft.github.io/language-server-protocol/) server for Solidity. The only currently supported communication channel is TCP.

Wake LSP server can be run using:

```shell
wake lsp
```

Or with an optional --port argument (default 65432):

```shell
wake lsp --port 1234
```

All LSP server features can be found in the [documentation](https://ackeeblockchain.com/wake/docs/latest/language-server/).

## License

This project is licensed under the [ISC license](https://github.com/Ackee-Blockchain/wake/blob/main/LICENSE).

## Partners

RockawayX             |  Coinbase
:-------------------------:|:-------------------------:
[![](https://github.com/Ackee-Blockchain/wake/blob/main/images/rockawayx.jpg?raw=true)](https://rockawayx.com/)  |  [![](https://github.com/Ackee-Blockchain/wake/blob/main/images/coinbase.png?raw=true)](https://www.coinbase.com/)






