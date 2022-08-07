// SPDX-License-Identifier: MIT
pragma solidity ^0.8;

interface IX {
    function test(IX arg) external;
}

library Lib {
    function test(IX arg) public pure returns(IX) {
        return arg;
    }
}

abstract contract A {
    function test1(A arg) public pure returns(A) {
        return arg;
    }
}

contract X {
    function test1(X arg) public pure returns(X) {
        return arg;
    }

    function test2(IX arg) public pure returns(IX) {
        return arg;
    }

    function test3(A arg) public pure returns(A) {
        return arg;
    }
}