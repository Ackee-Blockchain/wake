# Differential Testing

Example of testing a token contract with a differential testing approach.

```python
# Model class mirrors contract state
class TokenModel:
    balances: dict[Address, int]
    total_supply: int

    def transfer(self, from_: Address, to_: Address, amount: int):
        self.balances[from_] -= amount
        self.balances[to_] += amount

class ModelBasedTest(FuzzTest):
    token: Token
    model: TokenModel

    @flow()
    def flow_action(self):
        sender = random_account()
        recipient = random_account()
        amount = random_int(0, 1000)

        # Perform action on both contract and model
        self.token.transfer(recipient, amount, from_=sender)
        self.model.transfer(sender, recipient, amount)

    @invariant()
    def invariant_state(self):
        # Compare contract state with model
        assert self.token.balanceOf(user) == self.model.balances[user]
```