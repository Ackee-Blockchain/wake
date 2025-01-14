# Account Balance Testing

Testing account balances and registration in a contract that tracks user accounts and their balances.

```python
class AccountManagementTest(FuzzTest):
    accounts: dict[Address, bool]  # Track active accounts

    def pre_sequence(self):
        self.accounts = {}

    @flow()
    def flow_register_account(self):
        user = random_account(lower_bound=1)  # Skip account 0
        self.accounts[user.address] = True

    @invariant()
    def invariant_accounts(self):
        for account in self.accounts:
            assert self.contract.balanceOf(account) >= 0
```
