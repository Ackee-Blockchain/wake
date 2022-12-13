pragma solidity ^0.7;

contract C {
    bytes data;

    function legit_1(uint a) public {
        data.push("a");
        if (a == 0) {
            data.push("b");
        }
        else if (a == 1) {
            data.push("c");
        }
        else if (a == 2) {
            data.push("d");
        }
        else {
            data.push("e");
            revert("test");
        }
        data.push("f");

        for (int i = 0; i < 10; i++) {
            data.push("i");
        }
    }
}