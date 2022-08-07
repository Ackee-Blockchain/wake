// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8;

contract X {
    uint public constant CONST = 7;

    bytes3 public immutable IMMUT;

    mapping(address => address) public map;

    uint[] public arr;

    constructor() {
        IMMUT = "abc";
    }
}

// taken from https://docs.soliditylang.org/en/latest/contracts.html#getter-functions (modified)
contract Complex {
    struct Data {
        uint a;
        bytes3 b;
        mapping (uint => uint) map;
        uint[3] c;
        uint[] d;
        bytes e;
        Data[] dat;
    }
    mapping (uint => mapping(bool => Data[])) public data;
}
