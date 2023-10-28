import enum
import sys

if sys.version_info < (3, 11):

    class StrEnum(str, enum.Enum):
        pass

else:

    class StrEnum(enum.StrEnum):
        pass
