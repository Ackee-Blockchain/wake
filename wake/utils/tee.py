import sys
from abc import abstractmethod

# inspired by https://github.com/algrebe/python-tee/blob/master/tee/tee.py


class Tee:
    def __init__(self, filename, mode="a"):
        self.filename = filename
        self.mode = mode

        self.stream = None
        self.fp = None

    @abstractmethod
    def set_stream(self, stream):
        pass

    @abstractmethod
    def get_stream(self):
        pass

    def write(self, message):
        self.stream.write(message)  # pyright: ignore reportGeneralTypeIssues
        self.fp.write(message)  # pyright: ignore reportOptionalMemberAccess

    def flush(self):
        self.stream.flush()  # pyright: ignore reportGeneralTypeIssues
        self.fp.flush()  # pyright: ignore reportOptionalMemberAccess

    def __enter__(self):
        self.stream = self.get_stream()
        self.fp = open(self.filename, self.mode)
        self.set_stream(self)

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()

    def close(self):
        if self.stream is not None:
            self.set_stream(self.stream)
            self.stream = None

        if self.fp is not None:
            self.fp.close()
            self.fp = None

    def isatty(self):
        return self.stream.isatty()  # pyright: ignore reportGeneralTypeIssues

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.filename)

    __str__ = __repr__
    __unicode__ = __repr__


class StdoutTee(Tee):
    def set_stream(self, stream):
        sys.stdout = stream

    def get_stream(self):
        return sys.stdout


class StderrTee(Tee):
    def set_stream(self, stream):
        sys.stderr = stream

    def get_stream(self):
        return sys.stderr
