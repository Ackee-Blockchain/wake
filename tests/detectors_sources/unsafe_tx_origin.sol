//pragma solidity >=0.7
contract C {
    mapping(address => uint256) private _holderLastTransferTimestamp; // to hold last Transfers temporarily during launch
    address owner;

    function _msgOrigin() internal view virtual returns (address) {
        return tx.origin;
    }

    function _msgSender() internal view virtual returns (address) {
        return msg.sender;
    }

    function bug_1() public {
        address _caller = tx.origin;
        require(tx.origin == _caller, "bug1");
    }

    function bug_2() public {
        address _caller = _msgOrigin();
        require(tx.origin == _caller, "bug2");
    }

    function bug_3() public {
        address _caller = _msgSender();
        require(tx.origin > _caller, "bug3");
    }

    function bug_4() public {
        address _caller = owner;
        _caller = _msgSender();
        require(tx.origin > _caller, "bug4");
    }

    function bug_5() public {
        require(_holderLastTransferTimestamp[tx.origin] <= block.number, "bug5");
        _holderLastTransferTimestamp[tx.origin] = block.number;
    }

    function bug_6() public {
        require(_holderLastTransferTimestamp[tx.origin] > block.number - 3, "bug6");
        _holderLastTransferTimestamp[tx.origin] = block.number;
    }

    function legit_1() public {
        address _caller = _msgSender();
        require(tx.origin == _caller, "legit1");
    }

    function legit_2() public {
        address _caller = owner;
        _caller = msg.sender;
        require(tx.origin == _caller, "legit2");
    }

    function legit_3() public {
        address _caller = owner;
        _caller = msg.sender;
        require(_caller == _caller, "legit3");
    }

    function legit_4() public {
        require(_holderLastTransferTimestamp[tx.origin] < block.number, "legit4");
        _holderLastTransferTimestamp[tx.origin] = block.number;
    }
}