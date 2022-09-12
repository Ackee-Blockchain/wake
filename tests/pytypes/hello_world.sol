pragma solidity ^0.8.13;

contract HelloWorld{
    string public helloWorld = "Hello beautiful world!";
    uint256[] public testArr;
    uint256 public counter;
    address public addr;

    error Err(uint256 a);

    constructor(uint256 a) {
        counter = a;
    }

    function incrementCounter() public returns(uint256) {
        counter += 1;
        revert Err(counter);
        return counter;
    }

    function test(uint256 a) public returns(uint256) {
        return a;
    }

    fallback(bytes calldata input) external returns(bytes memory output) {
        (counter, addr) = abi.decode(input, (uint256, address));
        output = abi.encode(counter, addr);
    }
    
    //fallback() external {
    //    (counter, addr) = abi.decode(input, (uint256, address));
    //}

}