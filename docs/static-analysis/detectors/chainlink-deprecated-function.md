# Chainlink deprecated function detector

Name: `chainlink-deprecated-function`

Reports usage of deprecated Chainlink functions that should be replaced with their newer alternatives. These functions are part of the older Chainlink price feed interface and have been superseded by more recent versions.

## Example

```solidity hl_lines="5 9 13 17 21" linenums="1"
pragma solidity 0.8.0;

contract C {
    function getPrice() public view returns (int256) {
        return AggregatorV2V3Interface(priceFeed).latestAnswer(); // (1)!
    }

    function getTimestamp() public view returns (uint256) {
        return AggregatorV2V3Interface(priceFeed).latestTimestamp(); // (2)!
    }

    function getLatestRound() public view returns (uint256) {
        return AggregatorV2V3Interface(priceFeed).latestRound(); // (3)!
    }

    function getRoundData(uint256 roundId) public view returns (int256) {
        return AggregatorV2V3Interface(priceFeed).getAnswer(roundId); // (4)!
    }

    function getRoundTimestamp(uint256 roundId) public view returns (uint256) {
        return AggregatorV2V3Interface(priceFeed).getTimestamp(roundId); // (5)!
    }
}
```

1. `latestAnswer()` is deprecated. Use `latestRoundData()` instead.
2. `latestTimestamp()` is deprecated. Use `latestRoundData()` instead.
3. `latestRound()` is deprecated. Use `latestRoundData()` instead.
4. `getAnswer(uint256)` is deprecated. Use `getRoundData(uint80)` instead.
5. `getTimestamp(uint256)` is deprecated. Use `getRoundData(uint80)` instead.

## Parameters

The detector does not accept any additional parameters.