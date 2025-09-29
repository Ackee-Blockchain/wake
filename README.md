# Wake

The fastest fuzzing and testing framework for Solidity, written in Python.
Wake helps you write safer smart contracts, faster.

Built by [Ackee Blockchain Security](https://ackee.xyz) — trusted auditors of Lido, Safe, and Axelar.

![Wake cover](https://github.com/Ackee-Blockchain/wake/blob/main/images/wake_cover.png?raw=true)

---

## Why Wake?

Testing Solidity is hard. Unit tests only go so far, and hidden bugs surface under real-world transaction flows.
Wake fills the gap with:

- **Blazing-fast execution** — Python-native types and pytest integration
- **Built-in fuzzing & vulnerability detectors** — catch reentrancy, overflows, and logic flaws early
- **Seamless developer experience** — VS Code extension, GitHub Actions, solc manager
- **Cross-chain testing** — works with Anvil, Hardhat, and Ganache

---

## Features and benefits

- Testing framework based on [pytest](https://docs.pytest.org/en) — write clean, simple tests with familiar tooling
- Property-based fuzzer — automatically generate diverse inputs to uncover hidden bugs faster
- Deployments & mainnet interactions — test contracts in realistic environments before going live
- Vulnerability and code quality detectors — detect reentrancy, overflows, and bad patterns early in development
- Printers for extracting useful information from Solidity code — gain insights into contract structures and flows
- Static analysis framework for custom detectors and printers — extend Wake with project-specific rules
- GitHub actions for [setting up Wake](https://github.com/marketplace/actions/wake-setup) and [running detectors](https://github.com/marketplace/actions/wake-detect) — integrate seamlessly into CI/CD pipelines
- Language server ([LSP](https://microsoft.github.io/language-server-protocol/)) — get autocompletion, hints, and references inside your IDE
- VS Code extension ([Tools for Solidity](https://marketplace.visualstudio.com/items?itemName=AckeeBlockchain.tools-for-solidity)) — instant feedback while writing Solidity code
- Solc version manager — manage compiler versions with ease for consistent builds

---

## Wake vs other tools

![Wake vs other tools](https://github.com/Ackee-Blockchain/wake/blob/main/images/wake_vs_others.png?raw=true)

---

## Dependencies

- Python (version 3.8 or higher)
- Rosetta must be enabled on Apple Silicon Macs

## Installation

via `pip`

```shell
pip3 install eth-wake
```

## Discovered vulnerabilities

| Vulnerability                                   | Severity | Project | Method           | Discovered by    | Resources                                                                                                                                                                                                                       |
|-------------------------------------------------|----------|---------|------------------|------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Profit & loss accounted twice                   | Critical | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Loan refinancing reentrancy                     | Critical | PWN     | Detector         | Ackee Blockchain | [Report](https://github.com/PWNDAO/pwn_audits/blob/main/protocol/pwn-v1.3-ackee.pdf)                                                                                                                                            |
| Incorrect optimization in loan refinancing      | Critical | PWN     | Fuzz test        | Ackee Blockchain | [Report](https://github.com/PWNDAO/pwn_audits/blob/main/protocol/pwn-v1.3-ackee.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-pwn-protocol/blob/main/tests/test_refinance_comm_transfer_missing_found_fuzz.py)   |
| Console permanent denial of service             | High     | Brahma  | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-brahma-console-v2-report.pdf)                                                                                               |
| Swap unwinding formula error                    | High     | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Swap unwinding fee accounted twice              | High     | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Incorrect event data                            | High     | Solady  | Integration test | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-solady-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-solady/blob/main/tests/test_erc1155.py)          |
| `INTEREST_FROM_STRATEGY_BELOW_ZERO` reverts DoS | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Inaccurate hypothetical interest formula        | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Swap unwinding fee normalization error          | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Liquidation deposits accounted into LP balance  | Medium   | IPOR    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_st_eth_fuzz.py) |
| Missing receive function                        | Medium   | Axelar  | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-axelar-interchain-governance-executor/blob/main/tests/test_fuzz.py)                                                                                                      |
| `SafeERC20` not used for `approve`              | Medium   | Lido    | Fuzz test        | Ackee Blockchain | [Wake tests](https://github.com/Ackee-Blockchain/tests-lido-stonks/blob/main/tests/test_fuzz.py)                                                                                                                                |
| Non-optimistic vetting & unbonded keys bad accounting | Medium   | Lido    | Fuzz test        | Ackee Blockchain | [Report](https://github.com/lidofinance/audits/blob/main/Ackee%20Blockchain%20Lido%20Community%20Staking%20Module%20Report%2010-24.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-lido-csm/blob/main/tests/test_csm_fuzz.py) |
| Chainlink common denominator bad logic          | Medium   | PWN     | Fuzz test        | Ackee Blockchain | [Report](https://github.com/PWNDAO/pwn_audits/blob/main/protocol/pwn-v1.3-ackee.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-pwn-protocol/blob/main/tests/test_fuzz.py)                                         |
| Outdated/reverting Chainlink feed causes DoS    | Medium   | PWN     | Fuzz test        | Ackee Blockchain | [Report](https://github.com/PWNDAO/pwn_audits/blob/main/protocol/pwn-v1.3-ackee.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-pwn-protocol/blob/main/tests/test_fuzz.py)                                         |
| Incorrect EIP-712 typehash                      | Medium   | PWN     | Detector         | Ackee Blockchain | [Report](https://github.com/PWNDAO/pwn_audits/blob/main/protocol/pwn-v1.3-ackee.pdf)                                                                                                                                            |
| Incorrect EIP-712 data encoding                 | Medium   | PWN     | Fuzz test        | Ackee Blockchain | [Report](https://github.com/PWNDAO/pwn_audits/blob/main/protocol/pwn-v1.3-ackee.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-pwn-protocol/blob/revision-2.0/tests/test_fuzz.py)                                 |


---

## Features in-depth

### Fuzzer

Wake’s fuzzer builds on top of the testing framework and allows efficient fuzz testing of Solidity smart contracts.

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

@chain.connect()
def test_counter():
    CounterTest().run(sequences_count=30, flows_count=100)
```

---

### Detectors and printers

All vulnerability & code quality detectors can be run using:

```shell
wake detect all
```

Run a specific detector:

```shell
wake detect <detector-name>
```

See the [documentation](https://ackee.xyz/wake/docs/latest/static-analysis/using-detectors/) for a full list of detectors.

Run a printer:

```shell
wake print <printer-name>
```

See the [documentation](https://ackee.xyz/wake/docs/latest/static-analysis/using-printers/) for a full list of printers.

For custom detectors & printers, check the [getting started guide](https://ackee.xyz/wake/docs/latest/static-analysis/getting-started/) and repos for [wake_detectors](https://github.com/Ackee-Blockchain/wake/tree/main/wake_detectors) and [wake_printers](https://github.com/Ackee-Blockchain/wake/tree/main/wake_printers).

---

### LSP Server

Wake implements an [LSP](https://microsoft.github.io/language-server-protocol/) server for Solidity.
Run it with:

```shell
wake lsp
```

Or specify a port (default 65432):

```shell
wake lsp --port 1234
```

See all features in the [documentation](https://ackee.xyz/wake/docs/latest/language-server/).

---

## Documentation, contribution and community

- [Wake documentation](https://ackee.xyz/wake/docs/latest)
- [Contributing guide](https://ackee.xyz/wake/docs/latest/contributing/)
- [Follow X/Twitter](https://x.com/WakeFramework) for updates and tips


---

## License

This project is licensed under the [ISC license](https://github.com/Ackee-Blockchain/wake/blob/main/LICENSE).

---

## Partners

RockawayX             |  Coinbase
:-------------------------:|:-------------------------:
[![](https://github.com/Ackee-Blockchain/wake/blob/main/images/rockawayx.jpg?raw=true)](https://rockawayx.com/)  |  [![](https://github.com/Ackee-Blockchain/wake/blob/main/images/coinbase.png?raw=true)](https://www.coinbase.com/)
