import pytest

from woke import get_pi


@pytest.mark.platform_dependent
def test_pi():
    assert get_pi() == 3.1415
