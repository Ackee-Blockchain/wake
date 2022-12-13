pragma solidity ^0.7;

contract Parent {
    function func1(uint a) public returns (uint) {
        return a;
    }
}
contract Child is Parent {
    function func2(uint a) public {
        func1(a);
    }
}