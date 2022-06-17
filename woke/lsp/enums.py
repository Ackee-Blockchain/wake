import enum


class TraceValueEnum(str, enum.Enum):
    OFF = "off"
    MESSAGES = "messages"
    VERBOSE = "verbose"
