Woke testing framework is a Python-based framework for testing Solidity smart contracts.
It utilizes `pytypes`, Python equivalents of Solidity types, to maximize the tester's performance.

## Features

- auto-completions when writing tests thanks to `pytypes`
- property-based fuzzer leveraging multiprocessing to maximize the amount of inputs tested
- cross-chain testing support
- integrated Python debugger ([pdbr](https://github.com/cansarigol/pdbr)) attached on test failures
- call traces and `console.log` support for easier debugging
- better performance than other Python or JavaScript testing frameworks

The currently supported development chain implementations are:

- [Anvil](https://github.com/foundry-rs/foundry/tree/master/anvil)
- [Ganache](https://github.com/trufflesuite/ganache)
- [Hardhat](https://github.com/NomicFoundation/hardhat)