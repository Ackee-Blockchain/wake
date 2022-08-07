// SPDX-License-Identifier: MIT
pragma solidity ^0.8;

contract Xyz {
    function bool_(bool arg) public pure returns(bool) {
        return arg;
    }

    function uint128_(uint128 arg) external pure returns(uint136) {
        return arg;
    }

    function fixed_(fixed arg) public pure returns(fixed) {
        return arg;
    }

    function address_(address arg) public pure returns(address) {
        return arg;
    }

    function address_payable_(address payable arg) external pure returns(address payable) {
        return arg;
    }

    function bytes_(bytes calldata arg) public pure returns(bytes memory) {
        return arg;
    }

    function string_(string calldata arg) public pure returns(string memory) {
        return arg;
    }

    function bytes10_(bytes10 arg) public pure returns(bytes10) {
        return arg;
    }

    function function_(function (uint) external pure returns (uint) f) public pure returns(function (uint) external pure returns (uint)) {
        return f;
    }
}