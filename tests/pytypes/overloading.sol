// SPDX-License-Identifier: MIT
pragma solidity ^0.8;

struct A {
    uint x;
}

struct B {
    uint x;
}

enum E {
    TEST1,
    TEST2
}

type UserUint32 is uint32;

contract X {
    function test() external view {}

    function test(uint a) public pure {}

    function test(UserUint32 u) external pure {}

    function test(uint16 u) public pure {}

    function test(int i) external pure {}

    function test(E e) public pure {}

    function test(bool b) public pure {}

    function test(bytes1 x) external pure {}

    function test(bytes2 x) public pure {}

    function test(uint[] memory x) public payable {}

    function test(bytes[] calldata x) external pure {}

    function test(string[] calldata s) public pure {}

    function test(uint a, uint200 b) public pure {}

    function test(uint200 a, uint b) public pure {}

    function test(X x) external pure {}

    function test(A memory a) public pure {}

    function test(uint160 x) public pure {}

    function test(function (uint) external pure returns (uint) f) public pure returns(function (uint) external pure returns (uint)) {
        return f;
    }
}