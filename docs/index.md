# Woke

Woke is a Python-based development and testing framework for Solidity.

## Features
- testing framework
- property-based fuzzer
- vulnerability detectors
- LSP server

## Installation
Woke requires Python 3.7 or higher.

!!! warning
    Python 3.11 is experimentally supported.

### Using pip

```shell
pip3 install woke
```

## Shell completions

It is possible to enable shell completions for the `woke` command (does not apply to `woke-svm`).
The instructions depend on the shell you are using.

=== "Bash"
    Add the following to your `~/.bashrc` file:

    ```bash
    eval "$(_WOKE_COMPLETE=bash_source woke)"
    ```

=== "Zsh"
    Add the following to your `~/.zshrc` file:

    ```zsh
    eval "$(_WOKE_COMPLETE=zsh_source woke)"
    ```

=== "Fish"
    Add the following to your `~/.config/fish/completions/woke.fish` file:

    ```fish
    eval (env _WOKE_COMPLETE=fish_source woke)
    ```
