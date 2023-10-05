# Woke

Woke is a Python-based development and testing framework for Solidity.

Features:

- **Testing framework** - a testing framework for Solidity smart contracts with Python-native equivalents of Solidity types and blazing fast execution.

- **Fuzzer** - a property-based fuzzer for Solidity smart contracts that allows testers to write their fuzz tests in Python.

- **Vulnerability detectors**

- **LSP server**

## Dependencies

- [Python](https://www.python.org/downloads/release/python-3910/) (version 3.7 or higher)
- Rosetta must be enabled on Apple Silicon (M1 & M2) Macs

> :warning: Python 3.11 is experimentally supported.

## Installation

via `pip`

```shell
pip3 install woke
```

## Documentation & Contribution

Woke documentation can be found [here](https://ackeeblockchain.com/woke/docs/latest).

There you can also find a section on [contributing](https://ackeeblockchain.com/woke/docs/latest/contributing/).

## Discovered vulnerabilities

| Vulnerability                                   | Severity | Project | Method           | Discovered by    | Resources                                                                                                                                                                                                              |
|-------------------------------------------------|----------|---------|------------------|------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Profit & loss accounted twice                   | Critical | IPOR    | Fuzz test        | Ackee Blockchain | [Woke tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Swap unwinding formula error                    | High     | IPOR    | Fuzz test        | Ackee Blockchain | [Woke tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Swap unwinding fee accounted twice              | High     | IPOR    | Fuzz test        | Ackee Blockchain | [Woke tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Incorrect event data                            | High     | Solady  | Integration test | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-solady-report.pdf), [Woke tests](https://github.com/Ackee-Blockchain/tests-solady/blob/main/tests/test_erc1155.py) |
| `INTEREST_FROM_STRATEGY_BELOW_ZERO` reverts DoS | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Woke tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Inaccurate hypothetical interest formula        | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Woke tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Swap unwinding fee normalization error          | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Woke tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)                                                                                                                              |
| Missing receive function                        | Medium   | Axelar  | Fuzz test        | Ackee Blockchain | [Woke tests](https://github.com/Ackee-Blockchain/tests-axelar-interchain-governance-executor/blob/main/tests/test_fuzz.py)                                                                                             |

## Features

### Testing framework

See [examples](examples) and [documentation](https://ackeeblockchain.com/woke/docs/latest/testing-framework/overview) for more information.

Writing tests is as simple as:

```python
from woke.testing import *
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
from woke.testing import *
from woke.testing.fuzzing import *
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
woke detect
```

### LSP server

Woke implements an [LSP](https://microsoft.github.io/language-server-protocol/) server for Solidity. The only currently supported communication channel is TCP.

Woke LSP server can be run using:

```shell
woke lsp
```

Or with an optional --port argument (default 65432):

```shell
woke lsp --port 1234
```

All LSP server features can be found in the [documentation](https://ackeeblockchain.com/woke/docs/latest/language-server/).

## License

This project is licensed under the [ISC license](https://github.com/Ackee-Blockchain/woke/blob/main/LICENSE).

## Partners

RockawayX             |  Coinbase
:-------------------------:|:-------------------------:
[![](https://github.com/Ackee-Blockchain/woke/blob/main/images/rockawayx.jpg?raw=true)](https://rockawayx.com/)  |  [![](https://github.com/Ackee-Blockchain/woke/blob/main/images/coinbase.png?raw=true)](https://www.coinbase.com/)






