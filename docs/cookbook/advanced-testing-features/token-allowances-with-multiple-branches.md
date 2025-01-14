# Token Allowances with Multiple Branches

Example of testing a token contract with multiple branches in the transferFrom function.

```python
@flow()
def flow_transfer_from(self) -> None:
    sender = random_account()
    recipient = random_account()
    executor = random_account()
    insufficient_allowance = random_bool(true_prob=0.15)

    if insufficient_allowance:
        amount = random_int(self._allowances[sender][executor] + 1, 2**256 - 1)
        insufficient_balance = False
    else:
        amount = random_int(0, min(self._allowances[sender][executor], self._balances[sender]))
        insufficient_balance = random_bool(true_prob=0.15)
        if insufficient_balance:
            amount = random_int(self._balances[sender] + 1, 2**256 - 1)

    with may_revert() as e:
        self.token.transferFrom(sender, recipient, amount, from_=executor)

    if insufficient_allowance or insufficient_balance:
        assert e.value == Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW)
    else:
        self._balances[sender] -= amount
        self._balances[recipient] += amount
        self._allowances[sender][executor] -= amount
```
