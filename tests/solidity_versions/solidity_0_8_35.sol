// SPDX-License-Identifier: MIT
pragma solidity 0.8.35;

contract Solidity0835 layout at erc7201("wake.test.solidity-0.8.35") {
    uint256 public value;

    function assemblyValue() external pure returns (uint256 ret) {
        assembly {
            ret := 1
        }
    }
}
