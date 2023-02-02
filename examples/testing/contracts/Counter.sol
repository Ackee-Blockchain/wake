// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Counter {
    uint public count;
    address public owner;
    mapping(address => bool) public whitelist;

    event Incremented();
    event Decremented();
    event CountSet(uint count);

    error NotOwner();

    constructor() {
        owner = msg.sender;
        whitelist[msg.sender] = true;
    }

    function addToWhitelist(address _address) public {
        if (msg.sender != owner) revert NotOwner();
        whitelist[_address] = true;
    }

    function increment() public {
        count += 1;
        emit Incremented();
    }

    function setCount(uint _count) public {
        require(whitelist[msg.sender], "Only whitelisted addresses can set the count");
        count = _count;
        emit CountSet(_count);
    }

    function decrement() public {
        count -= 1;
        emit Decremented();
    }
}