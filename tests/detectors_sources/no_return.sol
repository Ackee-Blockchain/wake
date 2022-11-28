pragma solidity ^0.7;

abstract contract C {
    bytes data;

    function legit_1(uint a) public returns (bytes memory x) {
        data.push("a");
        if (a == 0) {
            x = data;
        }
        else {
            data.push("b");
            revert("bbb");
        }
    }

    function legit_2(uint a) public returns (bytes memory x) {
        data.push("a");
        if (a == 0) {
            return data;
        }
        else {
            data.push("b");
            revert("bbb");
        }
    }

    function legit_3(uint a) public returns (bytes memory x) {
        data.push("a");
        if (a == 0) {
            return data;
        }
        else {
            data.push("b");
            assembly {
                revert(add(32, 1), 1)
            }
        }
    }

    function legit_4(uint a, address addr) public returns (address x) {
        if (a == 0) {
            assembly {
                x := addr
            }
        }
        else {
            assembly {
                revert(add(32, 1), 1)
            }
        }
    }

    function legit_5(uint a) public returns (bytes memory x)
    {
        (data, x) = legit_6();
    }

    bytes d1;
    bytes d2;
    function legit_6() public returns (bytes memory, bytes memory)
    {
        return (d1,d2);
    }

    function legit_7(uint a) public returns (bytes memory x) {
        data.push("a");
        if (a == 0) {
            return data;
        }
        else {
            data.push("b");
        }
        return data;
    }

    function legit_9() public virtual returns (bytes memory x);

    function bug_no_return_stmt_1(uint a) public returns (bytes memory x) {
        data.push("a");
        if (a == 0) {
            data.push("b");
        }
        else {
            data.push("b");
            revert("bbb");
        }
    }

    function bug_no_return_stmt_2(uint a) public returns (bytes memory x) {
        data.push("a");
        if (a == 0) {
            x = data;
        }
        else {
            data.push("b");
        }
    }

    function bug_no_return_stmt_3(uint a) public returns (bytes memory, int x) {
        data.push("a");
        if (a == 0) {
            data.push("b");
            revert("bbb");
        }
    }

    function bug_no_vals_set_1(uint a, address addr) public returns (address x) {
        uint c = 3;
        if (a == 0) {
            assembly {
                c := 4
            }
        }
        else {
            assembly {
                revert(add(32, 1), 1)
            }
        }
    }

    function bug_no_vals_set_2(uint a) public returns (bytes memory x, address y) {
        data.push("a");
        if (a == 0) {
            x = data;
        }
        else {
            revert("aaa");
        }
    }

    function bug_no_vals_set_3(uint a) public returns (int x, int y) {
        data.push("a");
        if (a == 0) {
            revert("aaa");
        }
        else {
            assembly {
                x := 4
            }
        }
    }
}