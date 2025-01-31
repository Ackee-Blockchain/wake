# Chainlink Data Updating

Example of updating Chainlink aggregator data with new values.

```python
aggregator: AggregatorV3Interface

round_id, price = aggregator.latestRoundData()[:2]
change = price * random_int(1, 30) // 1000  # 0.01% - 3%
if random_bool():
    price += change
else:
    price -= change

write_storage_variable(
    aggregator, "s_hotVars", round_id, keys=["latestAggregatorRoundId"]
)
try:
    write_storage_variable(
        aggregator,
        "s_transmissions",
        {"answer": price, "timestamp": timestamp},
        keys=[round_id],
    )
except ValueError:
    # some aggregators have 3-member structs in s_transmissions
    write_storage_variable(
        aggregator,
        "s_transmissions",
        {
            "answer": price,
            "observationsTimestamp": timestamp,
            "transmissionTimestamp": timestamp,
        },
        keys=[round_id],
    )

assert aggregator.latestRoundData()[:2] == (round_id, price)
```