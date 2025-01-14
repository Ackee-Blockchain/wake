# Post-Sequence Cleanup

Example of testing a contract with a post-sequence cleanup function.

```python
class CleanupTest(FuzzTest):
    def post_sequence(self):
        # Clean up remaining balances
        for account in self.active_accounts:
            if self.contract.balanceOf(account) > 0:
                if random_bool():
                    self.withdraw(account, self.contract.balanceOf(account))

            if self.contract.claimable(account) > 0:
                if random_bool():
                    self.claim(account)

        # Verify final state
        self.verify_final_state()
```