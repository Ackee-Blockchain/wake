pragma solidity ^0.7;

contract Called {
    function receive_A() public payable returns (uint) {
        return 0xAA;
    }
}
contract Callee {
    function call(uint a, address _addr) payable public {
        if (a == 1)
        {
            Called(_addr).receive_A();
        }
        else if (a == 2)
        {
            (bool success, bytes memory data) = _addr.call{value: msg.value, gas: 5000}(abi.encodeWithSignature("receive_A()"));
        }
        else if (a == 3)
        {
            (bool success, bytes memory data) = _addr.delegatecall(abi.encodeWithSignature("receive_A()"));
        }
    }
}