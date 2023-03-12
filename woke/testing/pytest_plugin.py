from woke.config import WokeConfig
from woke.development.globals import reset_exception_handled


class PytestWokePlugin:
    _config: WokeConfig

    def __init__(self, config: WokeConfig):
        self._config = config

    def pytest_runtest_setup(self, item):
        reset_exception_handled()
