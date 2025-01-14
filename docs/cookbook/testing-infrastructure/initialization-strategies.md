# Initialization Strategies

Example of testing different initialization strategies for a factory contract.

```solidity
contract Factory {
    enum StrategyType { BASIC, ADVANCED, UPGRADEABLE, PROXY }

    error InvalidStrategy();
    error InvalidParams();

    struct BasicParams {
        address admin;
        uint256 value;
    }

    struct AdvancedParams {
        address admin;
        string name;
        uint8 version;
        uint256 config;
    }

    struct UpgradeableParams {
        address admin;
        address implementation;
        bytes initData;
    }

    struct ProxyParams {
        address admin;
        address logic;
        address proxy;
    }

    function deploy(
        bytes32 salt,
        StrategyType strategyType,
        bytes memory params
    ) external returns (address) {
        // Deploy contract based on strategy
    }
}
```

```python
@flow()
def flow_deploy_with_strategy(self) -> None:
    # Test different initialization strategies
    strategy_type = random_int(0, 3)
    admin = random_account()

    # Generate params based on strategy
    params = {
        0: self._encode_basic_params(
            admin=admin.address,
            value=random_int(0, 1000)
        ),
        1: self._encode_advanced_params(
            admin=admin.address,
            name=random_string(10),
            version=random_int(1, 5),
            config=random_int(0, 1000)
        ),
        2: self._encode_upgradeable_params(
            admin=admin.address,
            implementation=random_address(),
            init_data=random_bytes(32)
        ),
        3: self._encode_proxy_params(
            admin=admin.address,
            logic=random_address(),
            proxy=random_address()
        )
    }

    salt = random_bytes(32)

    with may_revert(Factory.InvalidStrategy) as e:
        self.factory.deploy(
            salt,
            strategy_type,
            params[strategy_type],
            from_=admin
        )

    if strategy_type > 3:
        assert e.value == Factory.InvalidStrategy()
    else:
        assert e.value is None
        deployed = self.factory.getDeployed(salt)
        self._validate_deployment(deployed, strategy_type, params[strategy_type])
```
