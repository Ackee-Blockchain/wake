import re


class SolidityImportExpr:
    """
    Solidity import expression parser. Correctness of a whole expression is checked, but only filename is extracted.
    At this stage, filename can be any Solidity string. No further checks are performed.
    """

    FILENAME = r"""(?P<filename>'.*[^\\]'|".*[^\\]")"""
    SYMBOL = r"[_a-zA-Z][_a-zA-Z0-9]*"
    ALIAS = r"\s*{symbol}(?:\s+as\s+{symbol})?\s*".format(symbol=SYMBOL)
    IMPORT_FILENAME_RE = re.compile(r"\s*{filename}\s*".format(filename=FILENAME))
    IMPORT_AS_FROM_RE = re.compile(
        r"\s*\*\s*as\s+{symbol}\s+from\s*{filename}\s*".format(
            filename=FILENAME, symbol=SYMBOL
        )
    )
    IMPORT_AS_RE = re.compile(
        r"\s*{filename}\s*as\s+{symbol}\s*".format(filename=FILENAME, symbol=SYMBOL)
    )
    IMPORT_ALIAS_LIST = re.compile(
        r"\s*{{{alias}(?:,{alias})*}}\s*from\s*{filename}\s*".format(
            alias=ALIAS, filename=FILENAME
        )
    )

    __filename: str

    def __init__(self, expr: str):
        cls = self.__class__
        res = (
            cls.IMPORT_FILENAME_RE,
            cls.IMPORT_AS_FROM_RE,
            cls.IMPORT_AS_RE,
            cls.IMPORT_ALIAS_LIST,
        )
        matches = list(re.match(expr) for re in res)

        if not any(matches):
            raise ValueError(f"Invalid import expression: `{expr}`")

        match = next(match for match in matches if match is not None)
        # strip leading and trailing quote and replace escapes
        self.__filename = (
            match.groupdict()["filename"][1:-1].replace("\\'", "'").replace('\\"', '"')
        )

    @property
    def filename(self):
        return self.__filename
