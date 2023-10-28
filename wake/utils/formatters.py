def format_wei(wei: int) -> str:
    if wei >= 10**15:
        # show as eth
        if wei >= 10**18 * 1000:
            # do not mix decimals and thousands
            return f"{round(wei / 10 ** 18):,} eth"
        return f"{(wei / 10 ** 18):.3g} eth"
    elif wei >= 10**6:
        # show as gwei
        if wei >= 10**9 * 1000:
            # do not mix decimals and thousands
            return f"{round(wei / 10 ** 9):,} gwei"
        return f"{(wei / 10 ** 9):.3g} gwei"
    else:
        return f"{wei:,} wei"
