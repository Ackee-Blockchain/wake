// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "wake/console.sol";

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

        console.log("Deployed a Counter with owner:", msg.sender);
    }

    function addToWhitelist(address _address) public {
        if (msg.sender != owner) revert NotOwner();
        whitelist[_address] = true;

        console.log("Added", _address, "to whitelist");
    }

    function increment() public {
        count += 1;
        emit Incremented();

        console.log("Incremented count to", count);
    }

    function setCount(uint _count) public {
        require(whitelist[msg.sender], "Only whitelisted addresses can set the count");
        count = _count;
        emit CountSet(_count);

        console.log("Set count to", count);
    }

    function decrement() public {
        count -= 1;
        emit Decremented();

        console.log("Decremented count to", count);
    }
}