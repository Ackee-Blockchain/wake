# Basic Fuzz Test Structure

The basic structure of a fuzz test.

```python
from wake.testing import *
from wake.testing.fuzzing import *

# Import the contract using pytypes path.
# The path is the same as the one used in the Solidity codebase.
from pytypes.contracts.Token import Token


class BasicFuzzTest(FuzzTest):
    token: Token  # Contract instance
    owner: Account

    def pre_sequence(self):
        self.owner = chain.accounts[0]
        self.token = Token.deploy("Name", "SYM", from_=self.owner)

    @flow()
    def flow_transfer(self):
        amount = random_int(1, 1000)
        user = random_account()
        self.token.transfer(user, amount, from_=self.owner)

    @invariant()
    def invariant_supply(self):
        assert self.token.totalSupply() == self.initial_supply


@chain.connect()
def test_basic():
    BasicFuzzTest().run(sequences_count=1, flows_count=100)
```