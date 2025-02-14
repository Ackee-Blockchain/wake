# Test Flow Branching

Example of testing a contract with branching logic in the test flow.

```python
class CrossAccountTest(FuzzTest):
    pool: Pool

    @flow()
    def flow_multi_account(self):
        user_count = random_int(1, 5)

        for _ in range(user_count):
            user = random_account(lower_bound=1).address

            if self.pool.balanceOf(user) == 0:
                self.pool.deposit(user, random_amount())
            else:
                self.pool.claim(user)

                if random_bool():
                    self.pool.deposit(user, random_amount())
                else:
                    balance = self.pool.balanceOf(user)
                    self.pool.withdraw(user, min(random_amount(), balance))
```