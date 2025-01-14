# Error Handling

Example of testing a complex function with multiple branches, including handling errors and ensuring all branches are covered.

```solidity
contract ComplexFunction {
    error InsufficientBalance();
    error InvalidAmount();
    error Unauthorized();

    function complexTransfer(
        address from,
        address to,
        uint256 amount,
        bytes calldata data
    ) external {
        if (amount == 0) revert InvalidAmount();
        if (balances[from] < amount) revert InsufficientBalance();
        if (!isAuthorized(msg.sender)) revert Unauthorized();

        if (data.length > 0) {
            // Complex path 1
            _handleData(data);
            balances[from] -= amount;
            balances[to] += amount;
        } else {
            // Complex path 2
            balances[from] -= amount;
            balances[to] += amount;
        }
    }
}
```

```python
@flow()
def flow_complex_transfer(self) -> None:
    # Test invalid amount branch
    with must_revert(ComplexFunction.InvalidAmount) as e:
        self.complex.complexTransfer(
            sender,
            recipient,
            0,
            b""
        )

    # Test insufficient balance branch
    amount = random_int(self._balances[sender] + 1, 2**256 - 1)
    with may_revert(ComplexFunction.InsufficientBalance) as e:
        self.complex.complexTransfer(
            sender,
            recipient,
            amount,
            b""
        )
        self._balances[sender] -= amount
        self._balances[recipient] += amount

    # Test unauthorized branch
    unauthorized = random_account()
    with must_revert(ComplexFunction.Unauthorized) as e:
        self.complex.complexTransfer(
            sender,
            recipient,
            100,
            b"",
            from_=unauthorized
        )

    # Test successful data path
    amount = random_int(0, self._balances[sender])
    data = random_bytes(1, 100)

    self.complex.complexTransfer(
        sender,
        recipient,
        amount,
        data,
        from_=authorized
    )

    self._balances[sender] -= amount
    self._balances[recipient] += amount
    self._validate_data_processed(data)

    # Test successful no-data path
    amount = random_int(0, self._balances[sender])
    self.complex.complexTransfer(
        sender,
        recipient,
        amount,
        b"",
        from_=authorized
    )

    self._balances[sender] -= amount
    self._balances[recipient] += amount
```

Example of testing complex inputs validation with different error handling scenarios.

```solidity
// Example of complex inputs validation
contract ComplexInputs {
    error InvalidSignature();
    error ExpiredDeadline();
    error InvalidNonce();

    struct ComplexParams {
        address owner;
        uint256 value;
        uint256 nonce;
        uint256 deadline;
        bytes signature;
    }

    function validateAndExecute(ComplexParams calldata params) external {
        if (params.deadline < block.timestamp) revert ExpiredDeadline();
        if (params.nonce != nonces[params.owner]) revert InvalidNonce();
        if (!_verify(params)) revert InvalidSignature();

        // Execute logic
        _execute(params);
    }
}
```

```python
@flow()
def flow_validate_complex_inputs(self) -> None:
    # Test expired deadline
    params = self._generate_valid_params()
    params.deadline = random_int(0, block.timestamp - 1)

    with must_revert(ComplexInputs.ExpiredDeadline):
        self.complex.validateAndExecute(params)

    # Test invalid nonce
    params = self._generate_valid_params()
    params.nonce = self._nonces[params.owner] + 1

    with must_revert(ComplexInputs.InvalidNonce):
        self.complex.validateAndExecute(params)

    # Test invalid signature
    params = self._generate_valid_params()
    params.signature = random_bytes(65)

    with must_revert(ComplexInputs.InvalidSignature):
        self.complex.validateAndExecute(params)

    # Test successful path
    params = self._generate_valid_params()
    self.complex.validateAndExecute(params)

    self._nonces[params.owner] += 1
    self._validate_execution(params)
```
