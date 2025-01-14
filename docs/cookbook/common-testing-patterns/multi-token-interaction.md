# Multi-Token Interaction

Example of testing a contract that interacts with multiple tokens.

```python
class MultiTokenTest(FuzzTest):
    token_a: Token
    token_b: Token

    def random_amount(self) -> int:
        return random_int(1, 10) * 10**18  # Handle decimals

    @flow()
    def flow_swap(self):
        amount = self.random_amount()
        user = random_account()

        # Approve and swap
        self.token_a.approve(self.pool, amount, from_=user)
        self.pool.swap(self.token_a, self.token_b, amount, from_=user)
```