import rich_click as click


@click.command(name="qr")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force generate new QR code.",
)
@click.pass_context
def run_qr(context: click.Context, force: bool) -> None:
    import qrcode

    from wake.config import WakeConfig

    config = WakeConfig(local_config_path=context.obj.get("local_config_path", None))
    config.load_configs()

    if "wake_remote" not in config.api_keys or force:
        import uuid

        wake_remote_key = str(uuid.uuid4())
        config.update({"api_keys": {"wake_remote": wake_remote_key}}, [])
        # global config path already made when WakeConfig was created
        wake_remote_file = config.global_config_path.parent / "wake_remote.txt"
        with wake_remote_file.open("w") as f:
            f.write(config.api_keys["wake_remote"])

    qr = qrcode.QRCode()
    qr.add_data(config.api_keys["wake_remote"])
    qr.print_ascii()
