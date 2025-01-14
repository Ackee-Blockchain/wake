# Context-Based Balance Tracking Pattern

Example of testing a token contract with a context-based balance tracking pattern.

```python
class BalanceTracker:
    def track_transfer(self, token, from_: Address, to: Address,
                      amount: int) -> tuple[int, int]:
        before_from = token.balanceOf(from_)
        before_to = token.balanceOf(to)

        yield

        after_from = token.balanceOf(from_)
        after_to = token.balanceOf(to)
        return (before_from - after_from, after_to - before_to)

class BalanceTest(FuzzTest):
    tracker: BalanceTracker

    @flow()
    def flow_transfer(self):
        with self.tracker.track_transfer(self.token, sender, receiver,
                                       amount) as changes:
            self.token.transfer(receiver, amount, from_=sender)

        delta_from, delta_to = changes
        assert delta_from == amount
        assert delta_to == amount
```