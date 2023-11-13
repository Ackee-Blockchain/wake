# Using printers

Printers are Python scripts used to extract useful information from Solidity smart contracts.
Wake is installed together with the [wake_printers](https://github.com/Ackee-Blockchain/wake/tree/main/wake_printers) module, which provides a set of printers for common use cases.

<div id="print-asciinema" style="z-index: 1; position: relative;"></div>
<script>
  window.onload = function(){
    AsciinemaPlayer.create('../print.cast', document.getElementById('print-asciinema'), { preload: true, autoPlay: true, rows: 28 });
}
</script>

## Basic usage

To list all available printers, run:

```bash
wake print --help
```

To run a printer, use:

```bash
wake print printer-name
```

A printer accepts a list of paths to contracts to be analyzed as arguments.
For example:

```bash
wake print inheritance-graph contracts/utils
```

## Printer configuration

Printers may accept additional arguments and options. To list them, run:

```bash
wake print printer-name --help
```

The output also describes environment variables that can be used to configure given arguments and options.

Additionally, printer configuration can be specified in the project-specific and global configuration TOML file, for example:

```toml title="wake.toml"
[printer."printer-name"]
custom_option = "value"
```

See [Configuration](../configuration.md) for more information.

## Changing printer loading priorities

Printers may be loaded from local directories:

- `./printers` (project-specific)
- `$XDG_DATA_HOME/wake/global-printers` (global)

and from printer packages (plugins), for example `wake_printers`.

A printer of the same name may be present in multiple packages (plugins). To see the list of available sources for each printer, run:

```bash
wake print list
```

Project-specific and global printers take precedence over printers from packages, with project-specific printers having the highest priority.

After that, printers are loaded from packages in the alphabetical order of package module names, making the first package the lowest priority.

The loading priorities can be changed in the global `plugins.toml` configuration file.
See [Configuration](../configuration.md#global-configuration-file) for more information.

