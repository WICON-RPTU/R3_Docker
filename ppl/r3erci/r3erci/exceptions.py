class ErciException(Exception):
    pass


class ResourceLocked(ErciException):
    pass


class TimeoutError(ErciException):
    pass


class ResponseError(ErciException):
    pass
