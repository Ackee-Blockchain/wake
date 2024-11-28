import rich_click as click


@click.command(name="qr")
def run_qr() -> None:
    import qrcode

    qr = qrcode.QRCode()
    qr.add_data("Some text")
    qr.print_ascii()
