from wake.config import WakeConfig
from wake.development.globals import reset_exception_handled


class PytestWakePlugin:
    _config: WakeConfig

    def __init__(self, config: WakeConfig):
        self._config = config

    def pytest_runtest_setup(self, item):
        reset_exception_handled()
