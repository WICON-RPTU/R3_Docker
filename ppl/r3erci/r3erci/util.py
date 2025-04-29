from datetime import datetime


class colors:
    OK = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"


def color_string(str, color):
    return f"{color}{str}{colors.ENDC}"


def color_string_fail(str):
    return color_string(str, colors.FAIL)


def color_string_success(str):
    return color_string(str, colors.OK)


def ts_print(msg=""):
    ts_str = datetime.strftime(datetime.now(), "%H:%M:%S.%f")
    print(ts_str, msg)
