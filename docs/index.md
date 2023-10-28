# Wake

Wake is a Python-based development and testing framework for Solidity.

## Features
- testing framework
- property-based fuzzer
- vulnerability detectors
- LSP server

## Installation
Wake requires Python 3.7 or higher.

!!! warning
    Python 3.11 is experimentally supported.

### Using pip

```shell
pip3 install eth-wake
```

## Shell completions

It is possible to enable shell completions for the `wake` command (does not apply to `wake-svm`).
The instructions depend on the shell you are using.

=== "Bash"
    Add the following to your `~/.bashrc` file:

    ```bash
    eval "$(_WAKE_COMPLETE=bash_source wake)"
    ```

=== "Zsh"
    Add the following to your `~/.zshrc` file:

    ```zsh
    eval "$(_WAKE_COMPLETE=zsh_source wake)"
    ```

=== "Fish"
    Add the following to your `~/.config/fish/completions/wake.fish` file:

    ```fish
    eval (env _WAKE_COMPLETE=fish_source wake)
    ```
