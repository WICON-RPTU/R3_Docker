from enum import IntEnum
from typing import Optional, Tuple
from r3erci.util import colors

RESERVED_VALUE = 0x0
PROTOCOL_VERSION = 0x3
PORT = 12200

MAC_ADDRESS_LENGTH = 6
SERIAL_NUMBER_LENGTH = 26
STAID_LENGTH = 2
CSI_LENGTH = 4

class CustomEnum(IntEnum):
    def __str__(self) -> str:
        return self.name


class ErciState(CustomEnum):
    INVALID = 0
    STARTUP = 1
    READY = 2
    RUNNING = 3
    RECONFIGURING = 4
    FAULT = 5
    MAINTENANCE = 6
    CONFIGURED = 7


class ErciCmd(CustomEnum):
    INVALID = 0
    SELECT_CONFIG = 1
    SWITCH_RING = 2
    START = 3
    STOP = 4
    COMMAND_RESULT = 5
    STATE_QUERY = 6
    STATE_RESPONSE = 7
    DIAGNOSTIC_DESCRIPTION_QUERY = 8
    DIAGNOSTIC_DESCRIPTION_RESPONSE = 9
    SWITCH_ANTENNA = 10
    SET_CONFIGMODE = 11
    PASSPORT_QUERY = 12
    PASSPORT_QUERY_RESPONSE = 13
    REBOOT = 128
    GET_CSI_QUERY = 129
    GET_CSI_RESPONSE = 130


class ErciInvalid(CustomEnum):
    CONFIG = 0
    RING = 0
    ANTENNA = 0


class ErciPosHeader(IntEnum):
    RESERVED = 0
    PROTOCOL_VERSION = 1
    COMMAND = 2
    SEQUENCE = 3


class ErciPosSelectConfig(IntEnum):
    CONFIG_ID = 4
    RING_ID = 5
    ANTENNA_ID = 6


class ErciPosSwitchRing(IntEnum):
    RING_ID = 4
    ANTENNA_ID = 5


class ErciPosCmdRes(IntEnum):
    CODE = 4
    MSG_START = 5


class ErciPosStateRes(IntEnum):
    STATE = 4
    CONFIG_ID = 5
    RING_ID = 6
    ANTENNA_ID = 7


class ErciPosDiagdesc(IntEnum):
    MSG_START = 4


class ErciPosSwitchAntenna(IntEnum):
    ANTENNA_ID = 4


class ErciPosSetConfigMode(IntEnum):
    CONFIG_MODE_FLAG = 4


class ErciPosPassportQuery(IntEnum):
    MAC_ADDRESS = 4
    SERIAL_NUMBER = 10


class ErciPosPassportQueryResponse(IntEnum):
    CODE = 4
    MAC_ADDRESS = 5
    SERIAL_NUMBER = 11

class ErciPosCsiGetResponse(IntEnum):
    CODE = 4
    STA_ID = 5
    CSI = 45

class ErciResultCode(CustomEnum):
    INVALID = 0
    SUCCESS = 65
    GENERIC_ERROR = 70
    WRONG_STATE = 71
    INVALID_MESSAGE_RECEIVED = 72
    INVALID_DATA_RECEIVED = 73
    NO_CONFIG_AVAILABLE = 74


class PacketLengthType(CustomEnum):
    INVALID = 0
    MINIMUM = 1
    EXACT = 2
    MAXIMUM = 3


def GetStateStringColor(state):
    if (
        (state == ErciState.INVALID)
        or (state == ErciState.FAULT)
        or (state == ErciState.MAINTENANCE)
    ):
        return colors.FAIL

    elif (
        (state == ErciState.STARTUP)
        or (state == ErciState.READY)
        or (state == ErciState.RUNNING)
    ):
        return colors.OK

    elif (state == ErciState.RECONFIGURING) or (state == ErciState.CONFIGURED):
        return colors.WARNING

    else:
        return colors.FAIL


def GetPacketLength(cmd: Optional[ErciCmd]) -> Tuple[Optional[int], PacketLengthType]:
    if cmd == ErciCmd.INVALID:
        raise Exception("Should never be requested.")
    elif cmd == ErciCmd.SELECT_CONFIG:
        return 7, PacketLengthType.EXACT
    elif cmd == ErciCmd.SWITCH_RING:
        return 6, PacketLengthType.EXACT
    elif (
        cmd == ErciCmd.START
        or cmd == ErciCmd.STOP
        or cmd == ErciCmd.STATE_QUERY
        or cmd == ErciCmd.DIAGNOSTIC_DESCRIPTION_QUERY
        or cmd == ErciCmd.REBOOT
    ):
        return 4, PacketLengthType.EXACT
    elif cmd == ErciCmd.COMMAND_RESULT:
        return 6, PacketLengthType.MINIMUM
    elif cmd == ErciCmd.STATE_RESPONSE:
        return 8, PacketLengthType.EXACT
    elif cmd == ErciCmd.DIAGNOSTIC_DESCRIPTION_RESPONSE:
        return 5, PacketLengthType.MINIMUM
    elif cmd == ErciCmd.SWITCH_ANTENNA:
        return 5, PacketLengthType.EXACT
    elif cmd == ErciCmd.SET_CONFIGMODE:
        return 5, PacketLengthType.EXACT
    elif cmd == ErciCmd.PASSPORT_QUERY:
        return 36, PacketLengthType.EXACT
    elif cmd == ErciCmd.PASSPORT_QUERY_RESPONSE:
        return 37, PacketLengthType.EXACT
    elif cmd == ErciCmd.GET_CSI_RESPONSE:
        return 805, PacketLengthType.MAXIMUM # erciData+status+20*staId+upperTriangularSnrMatrix 4B+1B+(20*2B)+(20*19/2*4B) but some are 0
    else:
        return 4, PacketLengthType.MINIMUM
