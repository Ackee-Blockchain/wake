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

## Discovered vulnerabilities

Wake is used by the Ackee Blockchain team to perform smart contract audits - and it helped to discover a bunch of high and critical vulnerabilities.

| Vulnerability                                   | Severity | Project | Method           | Resources                                                                                                                                                                                                                    |
|-------------------------------------------------|----------|---------|------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Profit & loss accounted twice                   | Critical | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Console permanent denial of service             | High     | Brahma  | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-brahma-console-v2-report.pdf)                                                                                            |
| Swap unwinding formula error                    | High     | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Swap unwinding fee accounted twice              | High     | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Incorrect event data                            | High     | Solady  | Integration test | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-solady-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-solady/blob/main/tests/test_erc1155.py)       |
| `INTEREST_FROM_STRATEGY_BELOW_ZERO` reverts DoS | Medium   | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Inaccurate hypothetical interest formula        | Medium   | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Swap unwinding fee normalization error          | Medium   | IPOR    | Fuzz test        | [Report](https://github.com/Ackee-Blockchain/public-audit-reports/blob/master/2023/ackee-blockchain-ipor-protocol-1-4-report.pdf), [Wake tests](https://github.com/Ackee-Blockchain/tests-ipor/blob/main/tests/test_fuzz.py) |
| Missing receive function                        | Medium   | Axelar  | Fuzz test        | [Wake tests](https://github.com/Ackee-Blockchain/tests-axelar-interchain-governance-executor/blob/main/tests/test_fuzz.py)                                                                                                   |