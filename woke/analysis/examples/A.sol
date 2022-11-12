// SPDX-License-Identifier: NONE

pragma solidity ^0.8.13;

contract ReceiveEther {
    // Function to receive Ether. msg.data must be empty
    receive() external payable {}

    // Fallback function is called when msg.data is not empty
    fallback() external payable {}

    function getBalance() public view returns (uint) {
        return address(this).balance;
    }
}