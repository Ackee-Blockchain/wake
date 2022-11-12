// SPDX-License-Identifier: NONE

pragma solidity ^0.8.13;

contract SendEtherNoPayable {
    function sendViaTransfer(address payable _to) public {
        // This function is no longer recommended for sending Ether.
        _to.transfer(100000);
    }

    function sendViaSend(address payable _to) public {
        // Send returns a boolean value indicating success or failure.
        // This function is not recommended for sending Ether.
        bool sent = _to.send(100000);
        require(sent, "Failed to send Ether");
    }

    function sendViaCall(address payable _to) public {
        // Call returns a boolean value indicating success or failure.
        // This is the current recommended method to use.
        (bool sent, bytes memory data) = _to.call{value: 100000}("");
        require(sent, "Failed to send Ether");
    }

        // Function to receive Ether. msg.data must be empty
    receive() external payable {
        revert ("Receive Ether");
    }

    // Fallback function is called when msg.data is not empty
    fallback() external payable {
        revert ("Receive Ether");
    }

}