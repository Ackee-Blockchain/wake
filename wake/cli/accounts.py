from pathlib import Path
from typing import List, Optional

import rich_click as click
from click.core import Context
from rich_click.rich_group import RichGroup

from .console import console


class NewCommandAlias(RichGroup):
    def get_command(self, ctx: Context, cmd_name: str):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        if cmd_name in {"new", "add", "create"}:
            return self.get_command(ctx, "new")
        if cmd_name in {"remove", "delete", "rm"}:
            return self.get_command(ctx, "remove")
        return None

    def resolve_command(self, ctx: Context, args: List[str]):
        _, cmd, args = super().resolve_command(ctx, args)
        return cmd.name if cmd is not None else None, cmd, args


@click.group(name="accounts", cls=NewCommandAlias)
@click.pass_context
def run_accounts(ctx: Context):
    """
    Run Wake accounts manager.
    """
    from eth_account import Account

    from wake.config import WakeConfig

    config = WakeConfig(local_config_path=ctx.obj.get("local_config_path", None))
    config.load_configs()
    ctx.obj["config"] = config

    Account.enable_unaudited_hdwallet_features()


@run_accounts.command(name="new")
@click.option("--kdf", default="scrypt", help="Key derivation function to encrypt key")
@click.option(
    "--password",
    prompt="Password to encrypt key",
    confirmation_prompt=True,
    default="",
    hide_input=True,
    help="Password to encrypt key",
)
@click.option(
    "--mnemonic/--no-mnemonic", is_flag=True, default=True, help="Print mnemonic"
)
@click.option("--language", "--lang", default="english", help="Mnemonic language")
@click.option("--words", default=12, help="Number of words")
@click.option("--hd-path", default="m/44'/60'/0'/0/0", help="HD path")
@click.option("--keystore", type=click.Path(file_okay=False), help="Keystore path")
@click.argument("alias")
@click.pass_context
def accounts_new(
    ctx: Context,
    kdf: str,
    password: str,
    mnemonic: bool,
    language: str,
    words: int,
    hd_path: str,
    keystore: Optional[str],
    alias: str,
):
    """
    Create a new account.
    """
    import json

    from eth_account import Account
    from eth_utils.address import to_checksum_address

    if keystore is None:
        path = Path(ctx.obj["config"].global_data_path) / "keystore"
    else:
        path = Path(keystore)
    if not path.exists():
        path.mkdir(parents=True)

    if not path.is_dir():
        raise click.BadParameter("Keystore path must be a directory")

    path = path / f"{alias}.json"
    if path.exists():
        raise click.BadParameter("Alias already exists, remove it first")

    if mnemonic:
        passphrase = click.prompt(
            "Mnemonic passphrase", default="", hide_input=True, confirmation_prompt=True
        )
        acc, mnemonic_str = Account.create_with_mnemonic(
            passphrase, words, language, hd_path
        )
        if click.confirm("Mnemonic will be printed, continue?"):
            console.print(f"[bold]{mnemonic_str}[/bold]")
    else:
        acc = Account.create()

    k = Account.encrypt(acc.key, password, kdf)

    with path.open("w") as f:
        json.dump(k, f)

    console.print(
        f"[green]Account created: {alias} {to_checksum_address(acc.address)}[/green]"
    )


@run_accounts.command(name="remove")
@click.option(
    "--keystore", type=click.Path(exists=True, file_okay=False), help="Keystore path"
)
@click.argument("alias")
@click.pass_context
def accounts_remove(ctx: Context, keystore: Optional[str], alias: str):
    """
    Remove an account.
    """
    import json

    from eth_utils.address import to_checksum_address

    if keystore is None:
        path = Path(ctx.obj["config"].global_data_path) / "keystore"
    else:
        path = Path(keystore)
    if not path.is_dir():
        raise click.BadParameter("Keystore path must be a directory")

    path = path / f"{alias}.json"
    if not path.exists():
        raise click.BadParameter("Alias does not exist")

    data = json.loads(path.read_text())
    path.unlink()
    console.print(
        f"[green]Account {to_checksum_address(data['address'])} removed[/green]"
    )


@run_accounts.command(name="list")
@click.option(
    "--keystore", type=click.Path(exists=True, file_okay=False), help="Keystore path"
)
@click.pass_context
def accounts_list(ctx: Context, keystore: Optional[str]):
    """
    List all accounts.
    """
    import json

    from eth_utils.address import to_checksum_address

    if keystore is None:
        path = Path(ctx.obj["config"].global_data_path) / "keystore"
    else:
        path = Path(keystore)
    if not path.is_dir():
        return

    for file in sorted(path.iterdir()):
        if file.suffix == ".json" and file.is_file():
            with file.open() as f:
                k = json.load(f)
            console.print(f"{file.stem}: {to_checksum_address(k['address'])}")


@run_accounts.command(name="import")
@click.option("--kdf", default="scrypt", help="Key derivation function to encrypt key")
@click.option(
    "--password",
    prompt="Password to encrypt key",
    confirmation_prompt=True,
    default="",
    hide_input=True,
    help="Password to encrypt key",
)
@click.option(
    "--hd-path", default="m/44'/60'/0'/0/0", help="HD path when importing mnemonic"
)
@click.option("--keystore", type=click.Path(file_okay=False), help="Keystore path")
@click.argument("alias")
@click.pass_context
def accounts_import(
    ctx: Context,
    kdf: str,
    password: str,
    hd_path: str,
    keystore: Optional[str],
    alias: str,
):
    """
    Import an account from a private key or mnemonic.
    """
    import json

    from eth_account import Account
    from eth_utils.address import to_checksum_address

    if keystore is None:
        path = Path(ctx.obj["config"].global_data_path) / "keystore"
    else:
        path = Path(keystore)
    if not path.exists():
        path.mkdir(parents=True)

    if not path.is_dir():
        raise click.BadParameter("Keystore path must be a directory")

    path = path / f"{alias}.json"
    if path.exists():
        raise click.BadParameter("Alias already exists, remove it first")

    key_or_mnemonic = click.prompt("Private key or mnemonic", hide_input=True)
    key = None

    if key_or_mnemonic.startswith("0x"):
        try:
            key = bytes.fromhex(key_or_mnemonic[2:])
        except ValueError:
            raise click.BadParameter("Invalid private key")

    if key is None:
        try:
            key = bytes.fromhex(key_or_mnemonic)
        except ValueError:
            key = None

    if key is not None:
        acc = Account.from_key(key)
    else:
        acc = Account.from_mnemonic(key_or_mnemonic, "", hd_path)

    k = Account.encrypt(acc.key, password, kdf)

    with path.open("w") as f:
        json.dump(k, f)

    console.print(
        f"[green]Account imported: {alias} {to_checksum_address(acc.address)}[/green]"
    )


@run_accounts.command(name="export")
@click.option(
    "--keystore", type=click.Path(exists=True, file_okay=False), help="Keystore path"
)
@click.argument("alias")
@click.pass_context
def accounts_export(ctx: Context, keystore: Optional[str], alias: str):
    """
    Export an account's private key.
    """
    import json

    from eth_account import Account
    from eth_utils.address import to_checksum_address

    if keystore is None:
        path = Path(ctx.obj["config"].global_data_path) / "keystore"
    else:
        path = Path(keystore)
    if not path.is_dir():
        raise click.BadParameter("Keystore path must be a directory")

    path = path / f"{alias}.json"
    if not path.exists():
        raise click.BadParameter("Alias does not exist")

    with path.open() as f:
        k = json.load(f)

    x = Account.decrypt(k, click.prompt("Password", default="", hide_input=True))
    console.print(
        f"[green]Address {to_checksum_address(k['address'])} with private key {x.hex()}[/green]"
    )
