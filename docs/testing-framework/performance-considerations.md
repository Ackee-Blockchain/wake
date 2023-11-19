# Performance considerations

Wake testing framework is designed to be fast and efficient. However, there are some things to keep in mind to achieve the best performance.

1. Always prefer to use [Anvil](https://github.com/foundry-rs/foundry/tree/master/crates/anvil) whenever possible.
2. Always prefer WebSockets connection over HTTP connection.
3. Avoid accessing transaction events (`tx.events`) unless necessary. Consider using `tx.raw_events` instead.
4. Avoid using accounts other than the pre-generated ones (`chain.accounts`) in `from_` parameters. If you need more accounts than the default number, change the Wake [configuration](../configuration.md) file or launch the development chain with a higher number of accounts and connect to it.
5. Minimize usage of call traces (`tx.call_trace`) and console logs (`tx.console_logs`). These features are useful for debugging, but may slow down the test execution.

## Profiling tests

Every Wake command has the `--profile` flag that can be used to profile the test execution. The profiling results are saved in the `.wake/wake.prof` file.

```shell
wake --profile test tests/test_counter.py
```

!!! warning
    It is important to specify the `--profile` flag before the `test` command.
    
    It is not recommended to profile the `wake test` command in multiprocessing mode (with the `-P` option set).

Wake uses cProfile [dump_stats](https://docs.python.org/3/library/profile.html#profile.Profile.dump_stats) method to save the profiling results.

!!! tip "Analyzing `wake.prof`"
    [gprof2dot](https://github.com/jrfonseca/gprof2dot) is a great tool for visualizing the profiling results.
    Together with [Graphviz](https://graphviz.org/), it can be used to generate a call graph of the test execution.
    
    ```shell
    gprof2dot -f pstats .wake/wake.prof | dot -Tsvg -o wake.prof.svg
    ```
