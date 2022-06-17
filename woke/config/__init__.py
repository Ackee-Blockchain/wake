from .woke_config import UnsupportedPlatformError, WokeConfig

__doc__ = """This module handles config file management. Each config option has its default value.
There are two main sources of config files:
* `config.toml` global config file in the Woke root directory ($HOME/.config/Woke on macOS and Linux, $HOME/Woke on Windows)
* `woke.toml` project-specific config file present in a project root directory

There may be additional config files included with the `subconfigs` top-level config key. Paths in the `subconfigs` key can
be both relative and absolute.

Config options can be overridden. Imported config options override the options in the original file. Order of files
listed in `subconfigs` also matters. Latter files in the list override earlier files. Config options loaded from the
global `config.toml` file can be overridden by options supplied through project-specific config files.

While this module enforces valid syntax of config files, it does not (and cannot) verify the semantics of the provided
config values. Extra config keys that are not specified in the documentation are forbidden."""
