pragma solidity /*a comment here*/ ^ 0.8.0;pragma solidity ~0.8.1;
// should be ignored pragma solidity 0.8.7;

/*
should be ignored pragma solidity 0.8.6;
*/

contract a {
    string malicious = '"should be \' ignored;pragma solidity 0.8.10;';
    string x = "123"; string malicious2 = 'should be ignored " \'pragma solidity 0.8.4;';
    string y = "123"; string malicious3 = "should be ignored \" \'pragma solidity 0.8.3;";
}
