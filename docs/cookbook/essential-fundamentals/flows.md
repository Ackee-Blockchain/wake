# Flows

Generation of flows for external functions and view functions.

```solidity
contract A {
    uint256 public a;
    function foo() external returns (uint256) { a = 1; }
}

contract B is A {
    function bar() external returns (uint256) { a = 2; }
    function view_baz() external view returns (uint256) { return 3; }
}
```

```python
class BTest(FuzzTest):
    b: B

    def pre_sequence(self):
        self.b = B.deploy()

    # Flows test all external functions that are not marked as view or pure
    @flow()
    def flow_foo(self):
        assert self.b.foo() == 1

    # One flow per external function
    @flow()
    def flow_bar(self):
        assert self.b.bar() == 2
```