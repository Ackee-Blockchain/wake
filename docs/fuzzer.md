# Woke fuzzer

Woke fuzzer is a property-based fuzzer for Solidity smart contracts that allows testers to write their fuzz tests in Python.

## Installation

!!! warning
    Woke fuzzer uses `brownie` package so be careful with your environment selection.

Woke fuzzer is an optional feature of Woke and can be installed with pip:
```
pip install abch-woke[fuzzer]
```

## Getting started

To get started, run the following command inside your project directory:
```
woke init fuzz
```

This command creates `pytypes` directory and generates your smart contract's [Python bindings](#python-bindings) and also copies an [example file](https://github.com/Ackee-Blockchain/woke/blob/main/woke/examples/fuzzer/test_example.py) `test_example.py` into `tests` directory.

Apart from having useful comments, this example file showcases basic structure of Woke fuzzer's fuzz tests which consists of:

* TestingSequence classes with methods decorated as **[Flows](#flows)** and **[Invariants](#invariants)** that are used for fuzz testing and an `__init__` method which is used for TestingSequence class setup and can also deploy the contract.
* `test_*` methods that run Woke fuzzer's Campaign with the TestingSequence class

!!! tip
    All of these can also be separated into multiple files, see more a [verbose directory structure](#recommended-directory-structure).

### TestingSequence and Campaign

TestingSequence is a tester defined class that specifies **[Flows](#flows)** and **[Invariants](#invariants)** that will be later used for fuzz testing and it is also used to set up any prerequisites such as contract deployment or instance attributes later used in tests (contract owner, etc.)

The Campaign class is a Woke fuzzer class that is responsible for the actual sequence generation and **[Flows](#flows)** and **[Invariants](#invariants)** execution from TestingSequence.
You can specify how many sequences of how many **[Flows](#flows)** you want to generate and execute using arguments in the `run` functions.
The development chain network gets reverted between the sequences.

In the example below, the contract is deployed and the Campaign is run with 1000 sequences consisting of 400 flows.

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

As you already know, a sequence of these **[Flows](#flows)** is generated and executed by the Campaign class. 

Notice that you can use `brownie.reverts` when you expect your transaction to be reverted.
Should a contract fail to revert the transaction, it will be reported as a bug by the fuzzer.

### Invariants

Woke fuzzer is a property-based fuzzer and as such it allows testers to define **[Invariant](#invariants)** methods with `@invariant` decorator. These **[Invariant](#invariants)** methods check for correctness of certain properties in deployed fuzzed smart contract after every **[Flow](#flows)** execution. 
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

* `random_account` chooses a random account from existing brownie accounts
* `random_int` generates random integer but with custom (increased) probabilities for `min`, `max` and `0`
* `random_bool` picks True/False randomly
* `random_string` can construct a random string of given `min` and `max` length
* `random_bytes` generates a sequence of random bytes with given `min` and `max` length

Some of the methods mentioned above also have other optional parameters such as predicates that can be used to further restrict which values will be generated, see [source code](https://github.com/Ackee-Blockchain/woke/blob/main/woke/fuzzer/random.py) for full specification.

### Running the fuzzer
When you've written your **[Flows](#flows)** and **[Invariants](#invariants)** you can let Woke fuzzer find all of the fuzz test files with:
```
woke fuzz
```
Or specify which fuzz tests you want to run:
```
woke fuzz ./tests/token_test.py
```

!!! info
    Woke fuzzer runs with [multiple processes by default](#fuzzing-with-multiple-processes). Be sure to check out `woke fuzz --help` for [optional CLI arguments](#optional-cli-arguments).

### Checking out the progress

While fuzzing you'll see progress report in the console stating how many processes are still running.
More verbose logs are stored in `.woke-logs/fuzz` directory, specifically the `latest` one for the last fuzzing campaign.

!!! tip
    We recommend using `less -r` to view the logs because they are ANSI code coloured.

### What to do when Woke fuzzer finds a bug

When Woke fuzzer finds a bug it will print out a standard Python traceback and asks if you want to attach the debugger.
Should you choose not to attach the debugger the fuzzing process will stop and you can later check out the execution log the same way as if you were [checking out the progress](#checking-out-the-progress).
If you decide to attach the debugger, you will see an IPython debugger instance which will allow you to explore the state of your fuzzing instance and dev chain. 

## Decorators
Apart from the `@flow` and `@invariant` that define type of the test method there are also decorators that can be used to tune **[Flow](#flows)** selection in a generated sequence:

* `@weight(x)` - specifies weight that will be used when generating a sequence with default weight being 100. Say flow1 has weight 1 and flow2 has weight 2, flow2 will have ~(2/3) of the executions and flow1 only ~(1/3)
* `@max_times(x)` - specifies maximum times a **[Flow](#flows)** will be called in one generated sequence
* `@ignore` - instructs Woke fuzzer to ignore this **[Flow](#flows)**, useful for testing and debugging

## Optional CLI arguments

```
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

Woke fuzzer supports fuzzing with multiple processes by default, so the simple commands above will spawn as many processes as you have cores. You can use `-n` to specify number of processes.

### Development chain

By default, woke fuzzer uses ganache-cli command to spawn a local dev chain for each process. 
It's important to have ports 8545 to (8545 + # of processes) free and bindable.

Woke fuzzer uses dev chain configuration from brownie so other development chains such as anvil can be selected with `--network` option, but make sure that brownie actually fully supports the dev chain.
As of now, only ganache seems to be fully supported for fuzzing.

### Seed selection

To make fuzzing reproducible, it's possible to specify a seed used when generating random data with `-s`.

### Passive mode

If you want to see more verbose output, try using the `--passive` mode that prints one process output into the console while still running other processes in the background.

## Python bindings
To make working with contracts a bit easier, Woke fuzzer generates Python bindings from your smart contract's ABI into the `pytypes` directory of your project.

## Recommended directory structure

For bigger projects, we recommend splitting up contract setup, **[Flow](#flows)** definition and `*_test.py` files.
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
    ├── token_test.py
    └── amm_test.py
```