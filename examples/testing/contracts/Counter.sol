// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Counter {
    uint public count;
    address public owner;
    mapping(address => bool) public whitelist;

    constructor() {
        owner = msg.sender;
        whitelist[msg.sender] = true;
    }

    function addToWhitelist(address _address) public {
        require(msg.sender == owner, "Only the owner can add to the whitelist");
        whitelist[_address] = true;
    }

    function increment() public {
        count += 1;
    }

    function setCount(uint _count) public {
        require(whitelist[msg.sender], "Only whitelisted addresses can set the count");
        count = _count;
    }

    function decrement() public {
        count -= 1;
    }
}