//pragma solidity >=0.6.0 <0.6.9;
contract C {
    bytes data;
    string data2;

    function legit_1() public returns (bytes memory) {
        // Empty byte array
        bytes memory t;
        // Store something else in memory after it
        uint[2] memory x;
        x[0] = type(uint).max;
        // Copy the empty byte array to storage,
        // this will copy too much from memory.
        data = t;
        // Create a new byte array element,
        // this will only update the length value.
        // legit
        data.push("a");
        // Now, `data[0]` is `0xff` instead of `0`.
        return data;
    }

    function bug_1() public returns (bytes memory) {
        // Empty byte array
        bytes memory t;
        // Store something else in memory after it
        uint[2] memory x;
        x[0] = type(uint).max;
        // Copy the empty byte array to storage,
        // this will copy too much from memory.
        data = t;
        // Create a new byte array element,
        // this will only update the length value.
        data.push();
        // Now, `data[0]` is `0xff` instead of `0`.
        return data;
    }

    function bug_2() public returns (bytes memory) {
        // Empty byte array
        bytes memory t;
        require(msg.sender==msg.sender);
        // Store something else in memory after it
        uint[2] memory x;
        require(msg.sender==msg.sender);
        x[0] = type(uint).max;
        require(msg.sender==msg.sender);
        // Copy the empty byte array to storage,
        // this will copy too much from memory.
        data = t;
        require(msg.sender==msg.sender);
        // Create a new byte array element,
        // this will only update the length value.
        data.push();
        require(msg.sender==msg.sender);
        // Now, `data[0]` is `0xff` instead of `0`.
        return data;
    }
}