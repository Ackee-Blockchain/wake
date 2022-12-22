pragma solidity ^0.7;

contract ParentParsing {
    constructor(string memory t)
    {
        string memory x=t;
    }
}

contract Parsing is ParentParsing {
    constructor() ParentParsing("test")
    {

    }

    modifier mod_test1(uint a) {
        require(a < 10);
        _;
    }

    modifier mod_test2(uint b) {
        require(b == 2 || b == 4 || b == 6);
        _;
    }

    function fcalls_func(uint a) mod_test1(a) mod_test2(a) public returns (uint b)
    {
        uint c = 3;
        b = if_func(a);
        c = 1;
    }

    function if_func(uint a) mod_test1(a) public returns (uint b) {
        if (a == 1) {
            b = 2;
        } else if (a == 2) {
            b = 3;
        } else if (a == 3) {
            b = 4;
        } else {
            b = 5;
        }
    }

    function for_func() public {
        assembly_func(3);
        int x = 3;
        for (int i = 0; i < 3; i++)
        {
            if (i == 1)
            {
                continue;
            }
            else if (i == 2)
            {
                break;
            }
        }
    }

    function assembly_func(uint256 a) public returns (uint) {
        if_func(a);
        a=3;
        assembly {
            let x := a
            if eq(x, 3) {
                x := 4
            }
            return (x, 0x20)
        }
    }
}