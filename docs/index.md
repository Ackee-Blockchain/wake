# Wake

[Wake](https://getwake.io) is a Python-based Solidity development and testing framework with built-in vulnerability detectors.

## Features
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

## Resources

- [Awesome Wake tests](https://github.com/Ackee-Blockchain/awesome-wake-tests) - collection of fuzz tests and unit tests written in Wake
- built-in [detectors](https://github.com/Ackee-Blockchain/wake/tree/main/wake_detectors) and [printers](https://github.com/Ackee-Blockchain/wake/tree/main/wake_printers)

## Discovered vulnerabilities

Wake is used by the Ackee team to perform smart contract audits - and it helped to discover a bunch of high and critical vulnerabilities.

| Vulnerability                                   | Severity | Project | Method           | Resources                                                                                                                                                                                                                       |
|-------------------------------------------------|----------|---------|------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Profit & loss accounted twice                   | Critical | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Console permanent denial of service             | High     | Brahma  | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-brahma-console-v2-report.pdf)                                                                                               |
| Swap unwinding formula error                    | High     | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Swap unwinding fee accounted twice              | High     | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Incorrect event data                            | High     | Solady  | Integration test | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-solady-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-solady/blob/main/tests/test_erc1155.py)          |
| `INTEREST_FROM_STRATEGY_BELOW_ZERO` reverts DoS | Medium   | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Inaccurate hypothetical interest formula        | Medium   | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Swap unwinding fee normalization error          | Medium   | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py)        |
| Liquidation deposits accounted into LP balance  | Medium   | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_st_eth_fuzz.py) |
| Missing receive function                        | Medium   | Axelar  | Fuzz test        | [Wake tests](https://github.com/Ackee-Blockchain/tests-axelar-interchain-governance-executor/blob/main/tests/test_fuzz.py)                                                                                                      |
| `SafeERC20` not used for `approve`              | Medium   | Lido    | Fuzz test        | [Wake tests](https://github.com/Ackee-Blockchain/tests-lido-stonks/blob/main/tests/test_fuzz.py)                                                                                                                                |
| Non-optimistic vetting & unbonded keys bad accounting | Medium   | Lido    | Fuzz test        | [Report](https://github.com/lidofinance/audits/blob/main/Ackee%20Blockchain%20Lido%20Community%20Staking%20Module%20Report%2010-24.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-lido-csm/blob/main/tests/test_csm_fuzz.py) |
