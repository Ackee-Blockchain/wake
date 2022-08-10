from collections import UserString


class StringReader(UserString):
    __original: str

    def __init__(self, original: str):
        self.__original = original
        super().__init__(original)

    def read(self, prefix: str) -> None:
        if self.startswith(prefix):
            self.data = self.data[len(prefix) :]
        else:
            raise ValueError(
                f"String does not start with '{prefix}'. Original: {self.__original}"
            )

    @property
    def original(self) -> str:
        return self.__original
