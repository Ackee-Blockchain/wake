# Installation
Wake requires Python 3.7 or higher.

!!! warning
    Python 3.12 is not supported yet.

## Using pip

```shell
pip3 install eth-wake
```

## Together with VS Code extension

`eth-wake` is automatically installed with the [Tools for Solidity](https://marketplace.visualstudio.com/items?itemName=AckeeBlockchain.tools-for-solidity) extension.

## Docker image

Wake is also available as a Docker image:

```shell
docker pull ackeeblockchain/wake
docker run -it ackeeblockchain/wake wake --help
```

## Github action

Wake comes with the `Ackee-Blockchain/wake-detect-action` Github action that can be used to run detectors on a Solidity codebase.
Refer to the [Wake detect action documentation](https://github.com/marketplace/actions/wake-detect) for more information.

## Shell completions

It is possible to enable shell completions for the `wake` command (does not apply to `wake-solc`).
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