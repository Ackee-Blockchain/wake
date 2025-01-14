# Error Tolerance

Example of testing a contract with a defined error tolerance for invariants.

```python
class PrecisionTest(FuzzTest):
    ERROR_TOLERANCE = 10**10  # Define acceptable rounding error

    @invariant()
    def invariant_with_tolerance(self):
        contract_value = self.contract.getValue()
        model_value = self.model.getValue()

        # Assert with tolerance
        assert abs(contract_value - model_value) < self.ERROR_TOLERANCE
```