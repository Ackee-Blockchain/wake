pragma solidity ^0.7.0;
interface Bug_ITest {
    function test() external;
}

interface Legit_ITest {
    function test() external;
}

contract InterfaceImplContract is Legit_ITest {
    function test() override external {

    }
}

library Bug_LibTest {
    function test(uint a, uint b) internal returns (uint)
    {
        return a + b;
    }

    function test2(uint a, uint b) internal returns (uint)
    {
        return a + b;
    }
}


library Legit_LibTest {
    function test(uint a, uint b) internal returns (uint)
    {
        return a + b;
    }

    function test2(uint a, uint b) internal returns (uint)
    {
        return a + b;
    }
}

contract LibraryTestContract {
    function lib_test() public
    {
        uint x = Legit_LibTest.test2(3, 5);
    }
}


abstract contract Bug_ATestContract {

}

abstract contract Legit_ATestContract {

}

contract ImplContract is Legit_ATestContract {
    function test() external {

    }
}

