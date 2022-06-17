import pytest

from woke.regex_parsing.solidity_import import SolidityImportExpr


def test_import_simple():
    assert SolidityImportExpr("'filename'").filename == "filename"
    assert SolidityImportExpr("*as symbolName from'filename'").filename == "filename"
    assert SolidityImportExpr("'filename'as symbolName").filename == "filename"
    assert (
        SolidityImportExpr("{symbol1 as alias,symbol2}from'filename'").filename
        == "filename"
    )


def test_import_whitespace():
    assert SolidityImportExpr("\r' \t filename'").filename == " \t filename"
    assert (
        SolidityImportExpr("\n*\ras\tsymbolName\r\n from '  f\tilename'").filename
        == "  f\tilename"
    )
    assert SolidityImportExpr("'filename\t'\tas\nsymbolName").filename == "filename\t"
    assert (
        SolidityImportExpr(
            "{\r\nsymbol1\ras   alias  \r,\t  \r\nsymbol2\n}\r\n \tfrom\n\r' filename '"
        ).filename
        == " filename "
    )


def test_import_escape():
    filename1 = r"""'\'filename\"'"""
    filename2 = r'''"\"filename\'"'''
    assert (
        SolidityImportExpr("{filename}".format(filename=filename1)).filename
        == "'filename\""
    )
    assert (
        SolidityImportExpr(
            "*as symbolName from {filename}".format(filename=filename2)
        ).filename
        == "\"filename'"
    )
    assert (
        SolidityImportExpr(
            "{filename}as symbolName".format(filename=filename1)
        ).filename
        == "'filename\""
    )
    assert (
        SolidityImportExpr(
            "{{symbol1 as alias,symbol2}}from{filename}".format(filename=filename2)
        ).filename
        == "\"filename'"
    )


def test_import_invalid():
    with pytest.raises(ValueError):
        SolidityImportExpr("'file\nname'")
    with pytest.raises(ValueError):
        SolidityImportExpr("*as symbolName from'f\nilename'")
    with pytest.raises(ValueError):
        SolidityImportExpr("* from 'abc.sol'")
