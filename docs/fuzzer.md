# Woke fuzzer

Woke fuzzer is a property-based fuzzer for Solidity smart contracts that allows testers to write their fuzz tests in Python.

## Installation

!!! warning
    Woke fuzzer uses [eth-brownie](https://eth-brownie.readthedocs.io/en/stable/) package. For this reason, it is recommended to install Woke fuzzer into a [virtual environment](https://docs.python.org/3/library/venv.html).
    It may be also needed to create a [brownie-config.yaml](https://eth-brownie.readthedocs.io/en/stable/config.html) configuration file so that Brownie can compile the project.

Woke fuzzer is an optional feature of Woke and can be installed with pip:
```shell
pip install woke[fuzzer]
```

## Getting started

To get started, run the following command inside the project directory:
```shell
woke init fuzz
```

This command creates `pytypes` directory, generates smart contract's [Python bindings](#python-bindings) and also copies an [example file](https://github.com/Ackee-Blockchain/woke/blob/main/woke/examples/fuzzer/test_example.py) `test_example.py` into `tests` directory.

Apart from having useful comments, this example file showcases basic structure of Woke fuzzer's fuzz tests which consists of:

* `TestingSequence` classes with methods decorated as **[Flows](#flows)** and **[Invariants](#invariants)** that are used for fuzz testing and an `__init__` method which is used for `TestingSequence` class setup and can also deploy contracts,
* `test_*` methods that run Woke fuzzer's `Campaign` with the `TestingSequence` class.

!!! tip
    All of these can also be separated into multiple files, see a [verbose directory structure](#recommended-directory-structure).

### `TestingSequence` and `Campaign`

`TestingSequence` is a tester defined class that specifies **[Flows](#flows)** and **[Invariants](#invariants)** that will be later used for fuzz testing and it is also used to set up any prerequisites such as contract deployment or instance attributes later used in tests (contract owner, etc.)

The `Campaign` class is a Woke fuzzer class that is responsible for the actual sequence generation and **[Flows](#flows)** and **[Invariants](#invariants)** execution from `TestingSequence`.
The number of generated sequences and **[Flows](#flows)** must be specified as arguments of the `run` function.
The development chain network gets reverted between the sequences.

In the example below, the contract is deployed and the `Campaign` is run with 1000 sequences consisting of 400 flows.

```python
import brownie
from pytypes import VotingContractType
from woke.fuzzer import Campaign
from woke.fuzzer.random import random_account

class TestingSequence:
    def __init(self, contract: VotingContractType):
        self.owner = random_account()
        self.contract = contract.deploy({"from": self.owner})
        self.subjects = {}
    
    # flows and invariants also go here

def test_campaign(voting_contract: VotingContractType):
    for _ in range(1):
        brownie.accounts.add()

    campaign = Campaign(lambda: TestingSequence(VotingContractType))
    campaign.run(1000, 400)
```

The number of execution times for a **[Flow](#flows)** per sequence can be tuned using [decorators](#decorators).

### Flows

A **[Flow](#flows)** is a test method with `@flow` decorator that uses the fuzzed smart contract and specifies where Woke fuzzer should insert randomly generated data. 
```python
import brownie
from woke.fuzzer.decorators import flow
from woke.fuzzer.random import random_account, random_string
...
    @flow
    def flow_add_subject(self):
        brownie.accounts.add()
        subject_name = random_string(0, 10)
        subject_account = random_account(
            predicate=lambda a: a != self.owner and a not in self.subjects
        )

        if len(subject_name) == 0 or subject_account in self.subjects:
            with brownie.reverts():
                self.contract.addSubject(subject_name, {"from": subject_account})
        else:
            self.contract.addSubject(subject_name, {"from": subject_account})
            self.subjects[subject_account] = (subject_name, 0)
```

A sequence of these **[Flows](#flows)** is generated and executed by the `Campaign` class.

`brownie.reverts` is used when a transaction is expected to revert.
Should a contract fail to revert the transaction, it will be reported as a bug by the fuzzer.

### Invariants

Woke fuzzer is a property-based fuzzer, and as such, it allows testers to define **[Invariant](#invariants)** methods with `@invariant` decorator. These **[Invariant](#invariants)** methods check for correctness of certain properties in deployed fuzzed smart contracts after every **[Flow](#flows)** execution.
```python
from woke.fuzzer.decorators import invariant
from woke.fuzzer.random import random_account
...
    @invariant
    def invariant_subjects(self):
        anyone = random_account()
        subjects = self.contract.getSubjects({"from": anyone})
        
        assert len(subjects) == len(self.subjects)
        
        for subject in subjects:
            anyone = random_account()
            subj = self.contract.getSubject(subject, {"from": anyone})
            assert self.subjects[subject][0] == subj["name"]
            assert self.subjects[subject][1] == subj["votes"]
```

Should any of the asserts in **[Invariant](#invariants)** method fail, it will be reported as a bug by the fuzzer.

### Generating pseudo-random data
Woke fuzzer has several built-in methods for generating pseudo-random data:

* `random_account` chooses a random account from existing brownie accounts,
* `random_int` generates random integer but with custom (increased) probabilities for `min`, `max` and `0`,
* `random_bool` picks True/False randomly,
* `random_string` can construct a random string of given `min` and `max` length,
* `random_bytes` generates a sequence of random bytes with given `min` and `max` length.

Some of the methods mentioned above also have other optional parameters such as predicates that can be used to further restrict which values will be generated, see [source code](https://github.com/Ackee-Blockchain/woke/blob/main/woke/fuzzer/random.py) for full specification.

### Running the fuzzer
After writing **[Flows](#flows)** and **[Invariants](#invariants)**, Woke fuzzer can be run with all fuzz test files using:
```
woke fuzz
```
Or with specified fuzz test files:
```
woke fuzz ./tests/test_token.py
```

!!! info
    Woke fuzzer runs with [multiple processes by default](#fuzzing-with-multiple-processes). Be sure to check out `woke fuzz --help` for [optional CLI arguments](#optional-cli-arguments).

### Checking out the progress

While fuzzing, the progress is reported in the console stating how many processes are still running.
More verbose logs are stored in `.woke-logs/fuzz` directory, specifically the `latest` one for the last fuzzing campaign.

!!! tip
    We recommend using `less -r` to view the log files because they are ANSI code coloured.

### What to do when Woke fuzzer finds a bug

When Woke fuzzer finds a bug, it will print out a standard Python traceback and ask if a debugger should be attached.
With the debugger not being attached, the current process is stopped but the rest of the processes continue fuzzing.
The bug can be later checked out in execution logs the same way as when [checking out the progress](#checking-out-the-progress).
With the debugger attached, [IPython debugger](https://github.com/gotcha/ipdb) instance is created which allows exploring the state of the fuzzing instance and development chain.

## Decorators
Apart from the `@flow` and `@invariant` that define type of the test method there are also decorators that can be used to tune **[Flow](#flows)** selection in a generated sequence:

* `@weight(x)` - specifies weight that will be used when generating a sequence with default weight being 100. Say flow1 has weight 100 and flow2 has weight 200, flow2 will have ~$\frac{2}{3}$ of the executions and flow1 only ~$\frac{1}{3}$,
* `@max_times(x)` - specifies maximum times a **[Flow](#flows)** will be called in one generated sequence,
* `@ignore` - instructs Woke fuzzer to ignore the decorated **[Flow](#flows)** or **[Invariant](#invariants)**, useful for testing and debugging.

## Optional CLI arguments

```console
$ woke fuzz --help
Usage: woke fuzz [OPTIONS] [PATHS]...

  Run Woke fuzzer.

Options:
  -n, --process-count INTEGER  Number of processes to create for fuzzing.
  -s, --seed TEXT              Random seeds
  --passive                    Print one process output into console, run
                               other in background.
  --network TEXT               Choose brownie dev chain. Default is
                               'development' for ganache
  --help                       Show this message and exit.

```

### Fuzzing with multiple processes

By default, Woke fuzzer performs fuzzing with a number of processes equal to the number of CPU cores. `-n` can be used to specify the number of processes.

### Development chain

`ganache-cli` is used as a default command to spawn a local dev chain for each process.
It's important to have ports 8545 to (8545 + # of processes) free and bindable.

Woke fuzzer uses dev chain configuration from Brownie so other development chains such as `anvil` or `hardhat` can be selected with `--network` option, but make sure that Brownie actually fully supports the dev chain.

### Random seed selection

To make fuzzing reproducible, it's possible to specify a seed used when generating random data with `-s`. With multiple seeds specified, each seed is assigned to a different process and the remaining seeds are generated randomly.

### Passive mode

For debugging purposes, it's possible to run Woke fuzzer in passive mode using the `--passive` option. In this mode, Woke fuzzer will print out the output of the process `#0` to the console.

## Python bindings
To make working with contracts a bit easier, Woke fuzzer generates Python bindings from smart contract's ABI into the `pytypes` directory of the project.

## Recommended directory structure

For bigger projects, we recommend splitting up contract setup, **[Flow](#flows)** definition and `test_*.py` files.
```
project/
├── contracts/
│   ├── Token.sol
│   └── Amm.sol
└── tests/
    ├── token
    │   ├── setup.py
    │   └── flows.py
    ├── amm
    │   ├── setup.py
    │   └── flows.py
    ├── __init__.py
    ├── test_token.py
    └── test_amm.py
```