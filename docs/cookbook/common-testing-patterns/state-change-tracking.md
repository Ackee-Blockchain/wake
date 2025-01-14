# State Change Tracking

Example of tracking complex state changes in a contract.

```python
class StateTracker:
    claimed: int
    total_reward: int
    balances: dict[Address, int]

    def track_claim(self, user: Address, amount: int):
        self.claimed += amount
        self.balances[user] += amount


class StateTrackingTest(FuzzTest):
    tracker: StateTracker

    @flow()
    def flow_claim(self):
        user = random_account()
        before = self.token.balanceOf(user)
        self.contract.claim(from_=user)
        after = self.token.balanceOf(user)

        claimed = after - before
        self.tracker.track_claim(user, claimed)
```