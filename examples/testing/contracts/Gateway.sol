// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Gateway {
    event Relay(address indexed target, bytes data, string destinationChain);

    address public immutable owner;

    constructor() {
        owner = msg.sender;
    }

    function relay(address target, bytes calldata data, string calldata destinationChain) external {
        emit Relay(target, data, destinationChain);
    }

    function execute(address target, bytes calldata data) external {
        require(msg.sender == owner, "only owner");
        (bool success, ) = target.call(data);
        require(success, "call failed");
    }
}