class PplException(Exception):
    pass

class TimeoutError(PplException):
    pass


class ResponseError(PplException):
    pass

""" Serialization related exceptions """

class DeserializeError(PplException):
    pass

class DeserializeVersionError(DeserializeError):
    def __init__(self, message: str, subprotocol, subprot_ver: int, sequence: int):
        super(DeserializeError, self).__init__(message)
        self.subprot = subprotocol
        self.subprot_version = subprot_ver
        self.sequence_number = sequence

class SerializeError(PplException):
    pass