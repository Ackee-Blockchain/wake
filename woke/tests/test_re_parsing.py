from pathlib import Path

from woke.c_regex_parsing import SoliditySourceParser


base_path = Path(__file__).parent.resolve() / "re_parsing_sources"


def test_a():
    path = base_path / "a.sol"
    versions, imports = SoliditySourceParser.parse(path)

    assert len(versions) == 1
    version_range = next(iter(versions))
    assert version_range.lower == "0.8.1"
    assert version_range.lower_inclusive
    assert version_range.higher == "0.9.0"
    assert not version_range.higher_inclusive

    assert len(imports) == 0


def test_b():
    path = base_path / "b.sol"
    versions, imports = SoliditySourceParser.parse(path)

    assert len(versions) == 1
    version_range = next(iter(versions))
    assert version_range.lower == "0.8.11"
    assert version_range.lower_inclusive
    assert version_range.higher == "0.9.2"
    assert version_range.higher_inclusive

    assert len(imports) == 1
    assert imports[0] == "a.sol"


def test_c():
    path = base_path / "c.sol"
    versions, imports = SoliditySourceParser.parse(path)

    assert len(versions) == 2
    it = iter(versions)
    range1 = next(it)
    range2 = next(it)
    assert ("0.8.0" not in range1) and ("0.8.0" not in range2)
    assert ("0.8.1" not in range1) and ("0.8.1" not in range2)
    assert ("0.9.0" not in range1) and ("0.9.0" not in range2)
    assert ("0.8.2" in range1) or ("0.8.2" in range2)
    assert ("0.8.9" in range1) or ("0.8.9" in range2)
    assert ("0.9.2" in range1) or ("0.9.2" in range2)

    assert len(imports) == 0


def test_d():
    path = base_path / "d.sol"
    versions, imports = SoliditySourceParser.parse(path)

    assert len(versions) == 1
    version_range = next(iter(versions))
    assert version_range.lower == "0.0.0"
    assert version_range.lower_inclusive
    assert version_range.higher is None
    assert version_range.higher_inclusive is None

    assert len(imports) == 3
    assert "abc_2$@#$'ax\"" in imports
    assert "'__  123\"" in imports
    assert "a.sol" in imports
