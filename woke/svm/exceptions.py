class ChecksumError(Exception):
    """
    Checksum of a downloaded file did not match the expected value.
    """


class UnsupportedVersionError(Exception):
    """
    The provided version is lower than the minimal supported version on the current platform.
    """
