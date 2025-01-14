# Logging with Formatting

Example of logging with formatting in a fuzz test.

```python
class FormattedLoggingTest(FuzzTest):
    def amount_str(self, amount: int) -> str:
        return str(amount / 10**18)  # Format with decimals

    @flow()
    def flow_with_logging(self):
        amount = random_amount()
        user = random_account()

        before = self.contract.balanceOf(user)
        self.contract.deposit(amount, from_=user)
        after = self.contract.balanceOf(user)

        log(f"[green]{user} deposits {self.amount_str(after - before)}[/]")
```