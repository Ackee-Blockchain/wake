import pytest

from woke.c_regex_parsing import SolidityVersion


def test_version_basic_usage():
    v1 = SolidityVersion("0.8.9")
    assert v1.major == 0
    assert v1.minor == 8
    assert v1.patch == 9

    v2 = SolidityVersion("0.8.7")
    assert v1 > v2
    v3 = SolidityVersion("0.8.9")
    assert v1 == v3
    v4 = SolidityVersion("0.8.9-abc+def")
    assert v3 == v4  # prerelease and build tags are ignored


def test_version_str_and_repr():
    s = "1.2.3-abc.def-012-ABC-abc+xyz-123.XYZ"
    v = SolidityVersion(s)
    assert str(v) == s
    assert eval(repr(v)) == v


def test_version_invalid():
    with pytest.raises(ValueError):
        SolidityVersion(">0.8.1")
    with pytest.raises(ValueError):
        SolidityVersion("=0.8.1")
    with pytest.raises(ValueError):
        SolidityVersion("v0.8.1")
    with pytest.raises(ValueError):
        SolidityVersion("x.8.1")
