# Time-Based Testing

Example of testing a contract with time-based operations.

```python
class TimeBasedTest(FuzzTest):
    day: int = 0

    @flow(weight=lambda self: min(self.day * 0.1, 0.5))
    def flow_time_sensitive(self):
        days_advance = random_int(1, 7)

        if self.day > 0:
            chain.mine(lambda x: x + days_advance * 86400)

        self.day += days_advance

        # Perform time-sensitive operations
        self.contract.update()
```