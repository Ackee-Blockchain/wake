# Multi-Token Accounting

Example of testing a contract that tracks multiple tokens and users.

```python
class TokenAccounting:
    balances: dict[Address, dict[Address, int]]  # token -> user -> amount

    def track_token(self, token: Address, user: Address, amount: int):
        if token not in self.balances:
            self.balances[token] = {}
        if user not in self.balances[token]:
            self.balances[token][user] = 0

        self.balances[token][user] += amount

    @invariant()
    def invariant_token_accounting(self):
        for token, users in self.balances.items():
            for user, amount in users.items():
                assert self.tokens[token].balanceOf(user) == amount
```