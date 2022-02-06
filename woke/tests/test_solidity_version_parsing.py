import pytest

from woke.c_regex_parsing import SolidityVersion, SolidityVersionRange


def test_version_basic_usage():
    v1 = SolidityVersion.fromstring("0.8.9")
    assert v1.major == 0
    assert v1.minor == 8
    assert v1.patch == 9

    v2 = SolidityVersion.fromstring("0.8.7")
    assert v1 > v2
    v3 = SolidityVersion.fromstring("0.8.9")
    assert v1 == v3
    v4 = SolidityVersion.fromstring("0.8.9-abc+def")
    assert v3 == v4  # prerelease and build tags are ignored


def test_version_str_and_repr():
    s = "1.2.3-abc.def-012-ABC-abc+xyz-123.XYZ"
    v = SolidityVersion.fromstring(s)
    assert str(v) == s
    assert eval(repr(v)) == v


def test_version_invalid():
    with pytest.raises(ValueError):
        SolidityVersion.fromstring(">0.8.1")
    with pytest.raises(ValueError):
        SolidityVersion.fromstring("=0.8.1")
    with pytest.raises(ValueError):
        SolidityVersion.fromstring("v0.8.1")
    with pytest.raises(ValueError):
        SolidityVersion.fromstring("x.8.1")


def test_version_range_basic():
    assert SolidityVersionRange(None, None, None, None) == SolidityVersionRange(
        "0.0.0", True, None, None
    )
    assert SolidityVersionRange("1.2.3", True, None, None) != SolidityVersionRange(
        "1.2.3", False, None, None
    )
    assert SolidityVersionRange(None, None, "3.4.5", True) != SolidityVersionRange(
        None, None, "3.4.5", False
    )

    r1 = SolidityVersionRange(None, None, None, None)
    assert not r1.isempty()
    assert r1.lower == SolidityVersion(0, 0, 0)
    assert r1.lower_inclusive
    assert r1.higher is None
    assert r1.higher_inclusive is None

    r2 = SolidityVersionRange("1.2.3", True, "3.4.5", False)
    assert not r2.isempty()
    assert r2.lower == SolidityVersion(1, 2, 3)
    assert r2.lower_inclusive
    assert r2.higher == SolidityVersion(3, 4, 5)
    assert not r2.higher_inclusive

    assert SolidityVersionRange("1.2.3", True, "0.9.9", False).isempty()
    assert SolidityVersionRange("1.2.3", True, "1.2.3", False).isempty()
    assert SolidityVersionRange("1.2.3", False, "1.2.3", True).isempty()
    assert SolidityVersionRange("1.2.3", False, "1.2.3", False).isempty()
    assert not SolidityVersionRange("1.2.3", True, "1.2.3", True).isempty()


def test_version_range_errors():
    r1 = SolidityVersionRange(None, None, None, None)
    with pytest.raises(ValueError):
        x = "abcd" in r1

    with pytest.raises(ValueError):
        SolidityVersionRange("-1.2.3", True, None, None)

    with pytest.raises(ValueError):
        SolidityVersionRange("1.2.3", None, None, None)
    with pytest.raises(ValueError):
        SolidityVersionRange(None, True, None, None)
    with pytest.raises(ValueError):
        SolidityVersionRange(None, None, "1.2.3", None)
    with pytest.raises(ValueError):
        SolidityVersionRange(None, None, None, True)


def test_version_range_contains():
    r1 = SolidityVersionRange("1.2.3", True, "2.0.0", False)
    assert SolidityVersion.fromstring("1.2.3") in r1
    assert "1.2.4" in r1
    assert "1.2.2" not in r1
    assert "2.0.0" not in r1
    assert "1.9.999" in r1

    r2 = SolidityVersionRange("0.8.9", False, "1.0.1", True)
    assert "0.8.9" not in r2
    assert "0.8.8" not in r2
    assert "0.8.10" in r2
    assert "1.0.1" in r2
    assert "1.0.0" in r2
    assert "0.9.9" in r2

    r3 = SolidityVersionRange("0.8.1", False, None, None)
    assert "0.8.1" not in r3
    assert "0.8.2" in r3
    assert "999999.999999.99999" in r3

    r4 = SolidityVersionRange("1.2.3", False, "0.1.2", False)
    assert r4.isempty()
    assert "0.0.0" not in r4
    assert "0.0.1" not in r4
    assert "0.1.2" not in r4
    assert "1.2.3" not in r4
    assert "1.2.4" not in r4


def test_version_range_str_and_repr():
    r1 = SolidityVersionRange(None, None, None, None)
    assert str(r1) == ">=0.0.0"
    assert eval(repr(r1)) == r1

    r2 = SolidityVersionRange("1.2.3", True, "4.5.6", False)
    assert str(r2) == ">=1.2.3 <4.5.6"
    assert eval(repr(r2)) == r2

    r3 = SolidityVersionRange("0.7.6", False, "2.0.7", True)
    assert str(r3) == ">0.7.6 <=2.0.7"
    assert eval(repr(r3)) == r3

    r4 = SolidityVersionRange("0.1.6", False, "0.0.8", True)
    assert r4.isempty()
    assert str(r4) == ">0.0.0 <0.0.0"
    assert eval(repr(r4)) == r4


def test_version_range_intersection():
    r1 = SolidityVersionRange("1.0.0", True, "2.0.0", True)
    r2 = SolidityVersionRange("1.0.1", False, None, None)
    assert r1 & r2 == SolidityVersionRange("1.0.1", False, "2.0.0", True)
    assert r1 & r2 == SolidityVersionRange.intersection(r1, r2)

    r3 = SolidityVersionRange("1.0.0", False, "2.0.0", False)
    assert r1 & r3 == r3
    assert r1 & r2 & r3 == r3 & r2 & r1
    assert r2 & r3 & r1 == SolidityVersionRange.intersection(r1, r3, r2)

    r4 = SolidityVersionRange("0.9.8", True, "1.9.8", False)
    assert r1 & r4 == SolidityVersionRange("1.0.0", True, "1.9.8", False)

    r5 = SolidityVersionRange("1.2.3", False, "2.0.1", False)
    assert r1 & r5 == SolidityVersionRange("1.2.3", False, "2.0.0", True)

    r6 = SolidityVersionRange(None, None, "1.0.0", False)
    r7 = SolidityVersionRange("2.0.0", False, None, None)
    assert (r1 & r6).isempty()
    assert r1 & r7

    r8 = SolidityVersionRange("0.0.0", False, "0.0.0", False)
    assert (r1 & r8).isempty()
