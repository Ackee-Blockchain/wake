// SPDX-License-Identifier: MIT
pragma solidity ^0.8;

enum State
{
    READY,
    WAITING
}

struct B
{
    State s;
    uint[] x;
}

struct Dummy
{
    Dummy[] x;
    mapping(address => Dummy) map;
}

contract A
{
    struct Test
    {
        uint a;
        B b;
    }

    function test1(Test memory a) public pure returns(Test memory) {
        return a;
    }

    function test2(Test calldata a) public pure returns(Test calldata) {
        return a;
    }
}