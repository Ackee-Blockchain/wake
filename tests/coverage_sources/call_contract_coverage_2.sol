pragma solidity ^0.7;

contract Called {
    function receive_A() public payable returns (uint) {
        return 0xAA;
    }
}