// SPDX-License-Identifier: MIT
pragma solidity ^0.8;

enum State
{
    READY,
    WAITING
}

contract X {
    enum Result
    {
        WAITING,
        FINISHED
    }

    function test1(State s) public pure returns(State) {
        return s;
    }

    function test2(Result r) public pure returns(Result) {
        return r;
    }
}