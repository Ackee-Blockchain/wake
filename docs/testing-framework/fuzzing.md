# Fuzzing

Fuzzing is a technique for testing software that involves providing invalid, unexpected, or random data as inputs to a computer program.

## Introduction

The Woke testing framework provides a `FuzzTest` class that can be used to write fuzz tests.
A `FuzzTest` can be run using the `run` method with two required arguments:

```python
class CounterTest(FuzzTest):
    ...

CounterTest().run(sequences_count=10, flows_count=100)
```

The first argument specifies the number of test sequences to be executed.
A sequence is an independent test case - all connected chains are reset after each sequence.
Each sequence consists of a given number of flows. A flow is an atomic test step that is executed in a test sequence.

The `FuzzTest` class provides two properties, `sequence_num` and `flow_num`, that can be used to obtain the current sequence and flow numbers, both starting from `0`.

### Flows

A flow is a single test step that is executed in a test sequence. Flows are defined using the `@flow` decorator:

```python
@flow(precondition=lambda self: self.count > 0)
def flow_decrement(self) -> None:
    self.counter.decrement(from_=random_account())
    self.count -= 1
```

Flow functions must be defined inside a test class that inherits from `FuzzTest`.

The `@flow` decorator accepts the following keyword arguments:

| Argument                    | Description                                                                                                                         |
|-----------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `weight`                    | weight defining probability of the flow being executed in a test sequence; defaults to `100`                                        |
| `max_times`                 | maximum number of times the flow can be executed in a test sequence; defaults to `None`                                             |
| <nobr>`precondition`</nobr> | function that accepts a single argument `self` and returns a boolean value; the flow is executed only if the precondition is `True` |

!!! example "How flow weights work"

        If a flow has a weight of `100` and another flow has a weight of `50`, the first flow will be executed twice as often as the second flow.

        ```python
        @flow(weight=100)
        def flow_1(self) -> None:
            ...

        @flow(weight=50)
        def flow_2(self) -> None:
            ...
        ```

        That means that the probability of `flow_1` being executed is `100 / (100 + 50) = 2/3` and the probability of `flow_2` being executed is `50 / (100 + 50) = 1/3`.

### Invariants

An invariant is a test that is executed after each flow in a test sequence. Invariants are defined using the `@invariant` decorator:

```python
@invariant(period=10)
def invariant_count(self) -> None:
    assert self.counter.count() == self.count
```

An optional `period` argument can be passed to the `@invariant` decorator. If specified, the invariant is executed only after every `period` flows.

### Execution hooks

Execution hooks are functions that are executed during the `FuzzTest` lifecycle. This is the list of all available execution hooks:

- `pre_sequence(self)` - executed before each test sequence
- `pre_flow(self, flow: Callable)` - executed before each flow, accepts the flow function to be executed as an argument
- `post_flow(self, flow: Callable)` - executed after each flow, accepts the flow function that was executed as an argument
- `pre_invariants(self)` - executed before each set of invariants
- `pre_invariant(self, invariant: Callable)` - executed before each invariant, accepts the invariant function to be executed as an argument
- `post_invariant(self, invariant: Callable)` - executed after each invariant, accepts the invariant function that was executed as an argument
- `post_invariants(self)` - executed after each set of invariants
- `post_sequence(self)` - executed after each test sequence

The whole `FuzzTest` lifecycle is visualized in the following diagram:

<div class="excalidraw">
--8<-- "docs/images/testing/FuzzTest-lifecycle.excalidraw.svg"
</div>

### Example

Putting all of the above together, here is an example of a `FuzzTest` that tests the `Counter` contract:

```python
from woke.testing import *
from woke.testing.fuzzing import *
from pytypes.contracts.Counter import Counter

class CounterTest(FuzzTest):
    counter: Counter
    count: int

    def pre_sequence(self) -> None:
        self.counter = Counter.deploy()
        self.count = 0

    @flow()
    def flow_increment(self) -> None:
        self.counter.increment()
        self.count += 1

    @flow()
    def flow_decrement(self) -> None:
        with may_revert(Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW)) as e:
            self.counter.decrement()

        if e.value is None:
            self.count -= 1
        else:
            assert self.count == 0

    @invariant(period=10)
    def invariant_count(self) -> None:
        assert self.counter.count() == self.count

@connect(default_chain)
def test_counter():
    default_chain.default_tx_account = default_chain.accounts[0]
    CounterTest().run(sequences_count=30, flows_count=100)
```

The test performs 30 test sequences, each consisting of 100 flows. It tests with two flows of the same probability: `flow_increment` and `flow_decrement`.
The invariant `invariant_count` is executed after every 10 flows.

## Generating random data

There are two ways to generate random data in Woke fuzz tests.

### Flow arguments

Every flow function can accept additional arguments to the implicit `self`. These arguments are generated based on the type hints:

```python
@flow()
def flow_set_count(self, count: uint) -> None:
    self.counter.set_count(count, from_=self.counter.owner())
    self.count = count
```

Flow argument types can be any of the following:

- integer types ranging from `uint8` to `uint256` and from `int8` to `int256`, including `uint` and `int`,
- byte types ranging from `bytes1` to `bytes32`, including `bytes` and `bytearray`,
- `List`, including `List1` to `List32` helper annotations (e.g. `List16[uint8]`),
- `bool`,
- `str`,
- `Address`, does never generate the zero address,
- any `Enum`, including enums generated in `pytypes`,
- any `dataclass`, including dataclasses generated in `pytypes`.

All flow arguments are generated non-biased, i.e. the probability of generating a value of a given type is the same for all values of that type.
For types that have length, the length is generated in the range 0 to 64.

For generating fine-tuned random data, it is recommended to use the random functions from the `woke.testing.fuzzing` module.

### Random functions

Woke testing framework provides a set of random functions that can be used to generate random data.

`random_account()` returns a random account from a given chain. It accepts the following keyword arguments:

| Argument                   | Description                                          | Default value                       |
|----------------------------|------------------------------------------------------|-------------------------------------|
| <nobr>`lower_bound`</nobr> | lower bound index of `chain.accounts` to choose from | `0`                                 |
| <nobr>`upper_bound`</nobr> | upper bound index of `chain.accounts` to choose from | `None` (i.e. `len(chain.accounts)`) |
| `predicate`                | predicate that the account must satisfy              | `None` (i.e. no predicate)          |
| `chain`                    | chain to choose the account from                     | `default_chain`                     |

`random_address()` returns a random address. It accepts the following keyword arguments:

| Argument            | Description                                | Default value |
|---------------------|--------------------------------------------|---------------|
| `zero_address_prob` | probability of generating the zero address | `0`           |

`random_int(min, max)` returns a random integer in the range `min` to `max`. It accepts the following keyword arguments:

| Argument                        | Description                                                            | Default value                       |
|---------------------------------|------------------------------------------------------------------------|-------------------------------------|
| `min_prob`                      | probability of generating `min`                                        | `None` (i.e. `1 / (max - min + 1))` |
| `max_prob`                      | probability of generating `max`                                        | `None` (i.e. `1 / (max - min + 1))` |
| `zero_prob`                     | probability of generating `0`, if `min` < `0` < `max`                  | `None` (i.e. `1 / (max - min + 1))` |
| <nobr>`edge_values_prob`</nobr> | value to use for `min_prob`, `max_prob` and<br> `zero_prob` if not set | `None`                              |

`random_bool()` returns a random boolean value. It accepts the following keyword arguments:

| Argument            | Description                                | Default value |
|---------------------|--------------------------------------------|---------------|
| `true_prob`         | probability of generating `True`           | `0.5`         |

`random_string(min, max)` returns a random string of length in the range `min` to `max`. It accepts the following keyword arguments:

| Argument                        | Description                                                        | Default value              |
|---------------------------------|--------------------------------------------------------------------|----------------------------|
| `alphabet`                      | alphabet to choose characters from                                 | `string.printable`         |
| `predicate`                     | predicate that the string must satisfy                             | `None` (i.e. no predicate) |

`random_bytes(min, max)` returns a random byte array of length in the range `min` to `max`. If `max` is not specified, it generates exactly `min` bytes.
It accepts the following keyword arguments:

| Argument                        | Description                                                        | Default value              |
|---------------------------------|--------------------------------------------------------------------|----------------------------|
| `predicate`                     | predicate that the byte array must satisfy                         | `None` (i.e. no predicate) |


## Launching tests in parallel

Woke testing framework allows running the same test in parallel with different random seeds.
Multiprocess tests are launched using the `woke fuzz` command:

```shell
woke fuzz tests/test_counter_fuzz.py -n 5
```

!!! info
    The command `woke fuzz` does not utilize the `pytest` framework to collect and execute tests.
    As a consequence, the `pytest` features like [fixtures](https://docs.pytest.org/en/stable/explanation/fixtures.html) are not available. Test functions must start with the `test` prefix.
    Test classes are not supported.

If a test process encounters an error, the user is prompted whether to debug the test or continue fuzzing.
While debugging, other processes are still running in the background.

<div id="woke-fuzz-asciinema" style="z-index: 1; position: relative;"></div>
<script>
  window.onload = function(){
    AsciinemaPlayer.create('../woke-fuzz.cast', document.getElementById('woke-fuzz-asciinema'), { preload: true, autoPlay: true, rows: 15 });
}
</script>

By default, nothing but status of each test is printed to the console. Using the `--passive` flag, the output of the first process is printed to the console.
Standard output and standard error of all processes are redirected to the `.woke-logs/fuzz` directory.

!!! tip "Reproducing a failed test"
    For every process, Woke generates a random seed that is used to initialize the random number generator.
    The seed is printed to the console and can be used to reproduce the test failure:

    ```shell
    woke fuzz tests/test_counter_fuzz.py -n 5 -s 62061e838798ad0f
    ```

    A random seed can be specified using the `-s` flag. Multiple `-s` flags are allowed.