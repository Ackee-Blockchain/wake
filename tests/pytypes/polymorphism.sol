// SPDX-License-Identifier: MIT
pragma solidity ^0.8;

interface IXyz {
    function allowance(address owner, address spender) external view returns (uint256);

    function bar() external pure returns(uint);

    function bar(uint) external pure returns(uint);
}

contract A is IXyz {
    mapping(address => mapping(address => uint256)) public override allowance;

    function foo() public pure virtual returns(uint) {
        return bar();
    }

    function bar() public pure virtual override returns(uint) {
        return 1;
    }

    function bar(uint x) public pure virtual override returns(uint) {
        return x;
    }
}

contract Def is A {
    function bar() public pure virtual override returns(uint) {
        return 2;
    }

    function bar(uint x) public pure virtual override returns(uint) {
        return 2 * x;
    }
}

contract Abc is A {
    function bar() public pure virtual override returns(uint) {
        return 3;
    }

    function bar(uint x) public pure virtual override returns(uint) {
        return 3 * x;
    }
}

contract B is Abc, Def {
    function foo() public pure override returns(uint) {
        return bar();
    }

    function bar() public pure virtual override(Abc, Def) returns(uint) {
        return 4;
    }

    function bar(uint x) public pure virtual override(Abc, Def) returns(uint) {
        return 4 * x;
    }
}

contract C is B {
    function bar() public pure override returns(uint) {
        return 5;
    }

    function bar(uint x) public pure virtual override returns(uint) {
        return 5 * x;
    }
}