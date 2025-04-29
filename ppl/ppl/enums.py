from enum import Enum, IntEnum


class AutoNumber(Enum):
    """Automatically generated Integer-Enum. See https://docs.python.org/3/library/enum.html#autonumber"""

    def __new__(cls):
        value = len(cls.__members__)
        obj = object.__new__(cls)
        obj._value_ = value
        return obj

    @classmethod
    def has_value(cls, value) -> bool:
        return any(value == item.value for item in cls)

    def __str__(self) -> str:
        return self.name

    def __int__(self):
        return int(self._value_)
    
class CapitalizedEnum(IntEnum):
    def capitalize(self, istr):
        words = istr.split("_")
        words = [x[0].upper() + x[1::].lower() for x in words]
        return " ".join(words)

    def __str__(self) -> str:
        return self.capitalize(self.name)
    

class MACOptimizations(IntEnum):
    NUM_STATIONS = 1
    RELIABILITY = 2
    MIN_LATENCY = 3
    EXACT_CONFIG = 4
    PAYLOAD_SIZE = 5

    def __str__(self) -> str:
        str_lut = {
            1: "# of Stations",
            2: "Reliability",
            3: "Min latency",
            4: "Exact Config",
            5: "Payload Size",
        }
        return str_lut[self.value]


class MACReliabilities(CapitalizedEnum):
    NONE = 1
    LOW = 2
    MODERATE = 3
    NORMAL = 4
    ADVANCED = 5
    HIGH = 6
    CRITICAL = 7
    EXTREME = 8

class SecurityMode(CapitalizedEnum):
    NONE = 0
    PAYLOAD_ENCRYPTION = 1
    FULL_ENCRYPTION = 2


class ConfigStorageMode(CapitalizedEnum):
    PERSIST = 0
    TEMPORARY = 1


def getOptimizationEnum(value: str) -> MACOptimizations:
    mapping = {
        "STATIONSMAX": MACOptimizations.NUM_STATIONS,
        "RELIABILITYMAX": MACOptimizations.RELIABILITY,
        "LATENCYMIN": MACOptimizations.MIN_LATENCY,
        "EXACT": MACOptimizations.EXACT_CONFIG,
        "PACKETLENMAX": MACOptimizations.PAYLOAD_SIZE,
    }
    return mapping.get(value.upper(), MACOptimizations.EXACT_CONFIG)

def getReliabilityEnum(value: str) -> MACReliabilities:
    mapping = {
        "NONE": MACReliabilities.NONE,
        "LOW": MACReliabilities.LOW,
        "MODERATE": MACReliabilities.MODERATE,
        "NORMAL": MACReliabilities.NORMAL,
        "ADVANCED": MACReliabilities.ADVANCED,
        "HIGH": MACReliabilities.HIGH,
        "CRITICAL": MACReliabilities.CRITICAL,
        "EXTREME": MACReliabilities.EXTREME,
    }
    return mapping.get(value.upper(), MACReliabilities.NONE)

def getSecurityModeEnum(value: str) -> SecurityMode:
    mapping = {
        "NONE": SecurityMode.NONE,
        "PAYLOAD_ENCRYPTION": SecurityMode.PAYLOAD_ENCRYPTION,
        "FULL_ENCRYPTION": SecurityMode.FULL_ENCRYPTION,
    }
    return mapping.get(value.upper(), SecurityMode.NONE)

class FilterAction(CapitalizedEnum):
    DROP = 0
    PRIORITY_1 = 1
    PRIORITY_2 = 2
    PRIORITY_3 = 3
    PRIORITY_4 = 4
    PRIORITY_5 = 5

def getFilterActionEnum(value: str) -> FilterAction:
    mapping = {
        "DROP": FilterAction.DROP,
        "PRIORITY_1": FilterAction.PRIORITY_1,
        "PRIORITY_2": FilterAction.PRIORITY_2,
        "PRIORITY_3": FilterAction.PRIORITY_3,
        "PRIORITY_4": FilterAction.PRIORITY_4,
        "PRIORITY_5": FilterAction.PRIORITY_5,
        "PRIO1": FilterAction.PRIORITY_1,
        "PRIO2": FilterAction.PRIORITY_2,
        "PRIO3": FilterAction.PRIORITY_3,
        "PRIO4": FilterAction.PRIORITY_4,
        "PRIO5": FilterAction.PRIORITY_5,
    }
    return mapping.get(value.upper(), SecurityMode.NONE)

class MeasType(CapitalizedEnum):
    MAC_TO_MAC = 0
    HOST_TO_HOST = 1

class SecurityMode(CapitalizedEnum):
    NONE = 0
    PAYLOAD_ENCRYPTION = 1
    FULL_ENCRYPTION = 2

class ifaceType(AutoNumber):
    INVALID = ()
    R3MAC = ()  # Device where an R3MAC is Running
    ETHERNET_MEAS = ()  # Ethernet device (candidate for measurement)
    ETHERNET = ()  # Ethernet device (not for measurement, e.g. main ETH)

class nodeState(AutoNumber):
    INVALID = ()
    STARTUP = ()  # The node is currently in startup. Will transition to idle on first pyrtmf packet or bridge on timeout
    IDLE = ()  # The node is idle. Version info of er0 will still be read
    PAIRED = ()  # The node is paired with a pyrtmf server, but not in a measurement
    RUNNING = ()  # The node is currently in a running measurement
    BRIDGED = ()  # The node is currently in bridging mode
    ERROR = ()  # The node has encountered a recoverable error during operation
    TAINTED = ()  # The node has encountered an unrecoverable error during operation. Nuke is required.

    # Active ndoeState: Paired with pyrtmf, in measurement or bridging
    def isActive(self) -> bool:
        return self in [self.PAIRED, self.RUNNING, self.BRIDGED]

    # IsIdle: Can be paired with
    def isIdle(self) -> bool:
        return self in [self.STARTUP, self.IDLE]
    
class nukeAction(AutoNumber):
    RESTART = ()
    SHUTDOWN = ()
    REBOOT = ()