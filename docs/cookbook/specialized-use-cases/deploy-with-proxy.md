# Deploy with Proxy

Example of deploying a contract with a proxy.

```solidity
contract Proxy is ERC1967Proxy {
    constructor(address implementation, bytes memory data) ERC1967Proxy(implementation, data) { ... }
}

contract MyContract {
    function initialize(address owner, uint256 arg) public { ... }
}
```

```python
impl = MyContract.deploy()
proxy = Proxy.deploy(impl, abi.encode(self.owner, 1))
self.my_contract = MyContract(proxy)
```
