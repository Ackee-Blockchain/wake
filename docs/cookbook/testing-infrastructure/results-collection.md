# Results Collection

Example of collecting and logging results from a contract.

```python
class TestResults:
    total_supply: int
    total_claimed: int
    balances: dict[Address, int]

    def collect_state(self, contract) -> None:
        self.total_supply = contract.totalSupply()
        self.total_claimed = contract.totalClaimed()

class ResultTrackingTest(FuzzTest):
    results: TestResults

    def post_sequence(self):
        self.results.collect_state(self.contract)
        self.log_results()
```
