# Axelar proxy `contractId` detector

Name: `axelar-proxy-contract-id`

The detector detects Axelar proxy and implementation contracts that use the `contractId` method as an additional check for deploying the contracts and when performing an upgrade.

## Proxy `contractId` shared between multiple contracts

Two different proxy contracts should not share the same `contractId`.

```solidity hl_lines="13 25" linenums="1"
pragma solidity ^0.8.0;

import { Proxy } from '@axelar-network/axelar-gmp-sdk-solidity/contracts/upgradable/Proxy.sol';

contract MyProxy is Proxy {
    constructor(
        address implementationAddress,
        address owner,
        bytes memory setupParams
    ) Proxy(implementationAddress, owner, setupParams) {}

    function contractId() internal pure virtual override returns (bytes32) {
        return keccak256('my-proxy');
    }
}

contract AnotherProxy is Proxy {
    constructor(
        address implementationAddress,
        address owner,
        bytes memory setupParams
    ) Proxy(implementationAddress, owner, setupParams) {}

    function contractId() internal pure virtual override returns (bytes32) {
        return keccak256('my-proxy');
    }
}
```

## Proxy contract without upgradeable contract with the same `contractId`

It is expected that a project will have at least one implementation contract with the same `contractId` as the proxy contract.
Proxy contracts without an implementation contract with the same `contractId` are reported.

## Implementation contract without proxy contract with the same `contractId`

It is expected that a project will have exactly one proxy contract with the same `contractId` as the implementation contract.
Implementation contracts without a proxy contract with the same `contractId` are reported.

## Proxy contract and upgradeable contract with function selector collision

An implementation contract and a corresponding proxy contract should not define functions with the same function selector.
It wouldn't be possible to call the implementation contract function in this case, as the proxy contract function would be called instead.

The `:::solidity implementation()` and `:::solidity setup(bytes calldata params)` functions are an exception to this rule and are not reported.

```solidity hl_lines="9-11 21-23" linenums="1"
pragma solidity ^0.8.0;

import { Proxy } from '@axelar-network/axelar-gmp-sdk-solidity/contracts/upgradable/Proxy.sol';
import { Upgradable } from '@axelar-network/axelar-gmp-sdk-solidity/contracts/upgradable/Upgradable.sol';

contract MyProxy is Proxy {
    constructor(address implementationAddress, address owner, bytes memory setupParams) Proxy(implementationAddress, owner, setupParams) {}

    function kind() external pure returns (string memory) {
        return 'proxy';
    }

    function contractId() internal pure virtual override returns (bytes32) {
        return keccak256('test');
    }
}

contract MyImplementation is Upgradable {
    constructor() Upgradable() {}

    function kind() external pure returns (string memory) {  // (1)!
        return 'implementation';
    }

    function contractId() external pure returns (bytes32) {
        return keccak256('test');
    }
}
```

1. It will never be possible to call the `kind` function of the implementation contract, as the proxy contract function will be called instead.

## Parameters

The detector does not accept any additional parameters.
