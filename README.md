# Wake, a Python-based Solidity development and testing framework with built-in vulnerability detectors

![Wake cover](https://github.com/Ackee-Blockchain/wake/blob/main/images/wake_cover.png?raw=true)

Features:

- testing framework based on [pytest](https://docs.pytest.org/en)
- property-based fuzzer
- deployments & mainnet interactions
- vulnerability and code quality detectors
- printers for extracting useful information from Solidity code
- static analysis framework for implementing custom detectors and printers
- Github actions for [setting up Wake](https://github.com/marketplace/actions/wake-setup) and [running detectors](https://github.com/marketplace/actions/wake-detect)
- language server ([LSP](https://microsoft.github.io/language-server-protocol/))
- VS Code extension ([Tools for Solidity](https://marketplace.visualstudio.com/items?itemName=AckeeBlockchain.tools-for-solidity))
- solc version manager

## Dependencies

- Python (version 3.7 or higher)
- Rosetta must be enabled on Apple Silicon Macs

> ⚠️ Python 3.12 is experimentally supported.

## Installation

via `pip`

```shell
pip3 install eth-wake
```

## Documentation & Contribution

Wake documentation can be found [here](https://ackeeblockchain.com/wake/docs/latest).

There you can also find a section on [contributing](https://ackeeblockchain.com/wake/docs/latest/contributing/).

## Discovered vulnerabilities

| Vulnerability                                   | Severity | Project | Method           | Discovered by    | Resources                                                                                                                                                                                                                    |
|-------------------------------------------------|----------|---------|------------------|------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Profit & loss accounted twice                   | Critical | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Console permanent denial of service             | High     | Brahma  | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-brahma-console-v2-report.pdf)                                                                                            |
| Swap unwinding formula error                    | High     | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Swap unwinding fee accounted twice              | High     | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Incorrect event data                            | High     | Solady  | Integration test | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-solady-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-solady/blob/main/tests/test_erc1155.py)       |
| `INTEREST_FROM_STRATEGY_BELOW_ZERO` reverts DoS | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Inaccurate hypothetical interest formula        | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Swap unwinding fee normalization error          | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Missing receive function                        | Medium   | Axelar  | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-axelar-interchain-governance-executor/blob/main/tests/test_fuzz.py)                                                                                                   |

## Features

### Testing framework

See [examples](https://github.com/Ackee-Blockchain/wake/tree/main/examples) and [documentation](https://ackeeblockchain.com/wake/docs/latest/testing-framework/overview) for more information.

Writing tests is as simple as:

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter

@default_chain.connect()
def test_counter():
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
        with may_revert(PanicCodeEnum.UNDERFLOW_OVERFLOW) as e:
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
    CounterTest().run(sequences_count=30, flows_count=100)
```

### Detectors

All vulnerability & code quality detectors can be run using:
```shell
wake detect all
```

A specific detector can be run using:
```shell
wake detect <detector-name>
```

See the [documentation](https://ackeeblockchain.com/wake/docs/latest/static-analysis/using-detectors/) for a list of all detectors.

### Printers

A specific printer can be run using:
```shell
wake print <printer-name>
```

See the [documentation](https://ackeeblockchain.com/wake/docs/latest/static-analysis/using-printers/) for a list of all printers.

### Custom detectors & printers

Refer to the [getting started](https://ackeeblockchain.com/wake/docs/latest/static-analysis/getting-started/) guide for more information.
Also check out [wake_detectors](https://github.com/Ackee-Blockchain/wake/tree/main/wake_detectors) and [wake_printers](https://github.com/Ackee-Blockchain/wake/tree/main/wake_printers) for the implementation of built-in detectors and printers.

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






