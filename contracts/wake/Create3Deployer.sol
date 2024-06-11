// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

import "./Create3.sol";

contract Create3Deployer {
    function deploy(bytes32 _salt, bytes memory _creationCode) external returns (address addr) {
        return Create3.create3(_salt, _creationCode);
    }

    function deployWithValue(bytes32 _salt, bytes memory _creationCode, uint256 _value) external returns (address addr) {
        return Create3.create3(_salt, _creationCode, _value);
    }

    function computeAddress(bytes32 _salt) external view returns (address addr) {
        return Create3.addressOf(_salt);
    }
}