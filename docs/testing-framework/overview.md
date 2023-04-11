---
title: Development and testing framework
---

Woke development and testing framework is a Python-based framework for testing and deploying Solidity smart contracts.
It utilizes `pytypes`, Python equivalents of Solidity types, to simplify writing scripts and easily discover typing errors.

## Features

- auto-completions when writing tests and deployment scripts thanks to `pytypes`
- type checking for all types generated in `pytypes`
- property-based fuzzer leveraging multiprocessing to maximize the amount of inputs tested
- cross-chain testing support
- integrated Python debugger ([ipdb](https://github.com/gotcha/ipdb)) attached on test failures
- call traces and `console.log` support for easier debugging
- deployment scripts support
- better performance than other Python or JavaScript frameworks

The currently supported development chains are:

- [Anvil](https://github.com/foundry-rs/foundry/tree/master/anvil) (recommended)
- [Ganache](https://github.com/trufflesuite/ganache)
- [Hardhat](https://github.com/NomicFoundation/hardhat)