import asyncio
from ipaddress import IPv4Address
from typing import NamedTuple, Optional, Tuple

from r3erci.constants import (
    PORT,
    PROTOCOL_VERSION,
    RESERVED_VALUE,
    ErciCmd,
    ErciInvalid,
    ErciPosHeader,
    ErciPosSelectConfig,
    ErciPosSwitchRing,
    ErciPosSwitchAntenna,
    ErciPosSetConfigMode,
    ErciResultCode,
    ErciState,
    GetPacketLength,
)
from r3erci.constants import PacketLengthType as PLT
from r3erci.exceptions import ResponseError
from r3erci.udpServer import UdpServer
from r3erci.util import ts_print, color_string_fail, colors

queue_tuple = NamedTuple("queue_tuple", [("data", bytes), ("address", Tuple[str, int])])


class StandaloneServer(UdpServer):
    queuedPackets = asyncio.Queue()  # type: asyncio.Queue[queue_tuple]

    def __init__(self):
        super().__init__()
        ts_print("r3erci running in standalone mode")
        self.handlerFuture = asyncio.ensure_future(self.handlePackets())

        self.erebStates = {}

    def shutdown(self):
        if self.handlerFuture:
            self.handlerFuture.cancel()
            self.handlerFuture = None

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass

    def createMessage(self, command: ErciCmd, sequence: int, otherdata: bytes) -> bytes:
        data = bytearray()
        data.append(RESERVED_VALUE)
        data.append(PROTOCOL_VERSION)
        data.append(int(command))
        data.append(sequence)
        if otherdata:
            for b in otherdata:
                data.append(b)
        return data

    def enqueuePacket(self, data: bytes, address: IPv4Address) -> None:
        self.queuedPackets.put_nowait(
            queue_tuple(
                data,
                (str(address), PORT),
            )
        )

    async def pumpPackets(self, timeout: Optional[float] = None) -> None:
        while (not self.queuedPackets.empty()) or timeout is not None:
            try:
                curr = await asyncio.wait_for(self.queuedPackets.get(), timeout)
            except asyncio.TimeoutError:
                return
            await self.receiveHandler(curr.data, curr.address)
            self.queuedPackets.task_done()

    async def handlePackets(self) -> None:
        while True:
            await self.pumpPackets(0.1)

    def enqueueCommandResult(
        self, address: IPv4Address, seq: int, code: ErciResultCode, status_msg=None
    ):
        otherdata = bytearray()
        otherdata.append(code)
        if status_msg:
            otherdata += bytearray(status_msg, encoding="utf-8")
        otherdata.append(0)
        self.enqueuePacket(
            self.createMessage(ErciCmd.COMMAND_RESULT, seq, otherdata), address
        )

    def sendPacket(self, data: bytes, address: IPv4Address, port: int) -> None:
        le, plt = GetPacketLength(None)
        if len(data) < le:
            ts_print(
                f"STANDALONE: Short frame! ({len(data)}B vs. expect {str(plt).lower()} {le}B)!"
            )
            # TODO: How would the EREB respond wo/ knowing the seq?
            self.enqueueCommandResult(
                address,
                255,
                ErciResultCode.INVALID_DATA_RECEIVED,
                status_msg="Short frame.",
            )
            return

        cmd = data[ErciPosHeader.COMMAND]
        seq = data[ErciPosHeader.SEQUENCE]

        ts_print(f"STANDALONE: Have command {str(ErciCmd(cmd))} for station {address}")

        if data[ErciPosHeader.RESERVED] != RESERVED_VALUE:
            ts_print(f"STANDALONE: Reserved field not {RESERVED_VALUE}!")
            return

        if data[ErciPosHeader.PROTOCOL_VERSION] != PROTOCOL_VERSION:
            ts_print(f"STANDALONE: Version field not 0x{PROTOCOL_VERSION}!")
            return

        if (
            cmd == ErciCmd.INVALID
            or cmd == ErciCmd.COMMAND_RESULT
            or cmd == ErciCmd.STATE_RESPONSE
        ):
            ts_print(
                f"STANDALONE: Command {str(ErciCmd(cmd))} should not have been received. ({bytes(data)})"
            )
            self.enqueueCommandResult(
                address, seq, ErciResultCode.INVALID_MESSAGE_RECEIVED
            )

        le, plt = GetPacketLength(cmd)
        if plt == PLT.MINIMUM:
            if len(data) < le:
                ts_print(
                    f"STANDALONE: {color_string_fail('Short frame!')} ({len(data)}B vs. expect {str(plt).lower()} {le}B)"
                )
                self.enqueueCommandResult(
                    address,
                    seq,
                    ErciResultCode.INVALID_DATA_RECEIVED,
                    status_msg="Short frame.",
                )
                return
        elif plt == PLT.EXACT:
            if len(data) != le:
                ts_print(
                    f"STANDALONE: {color_string_fail('Wrong frame length!')} ({len(data)}B vs. expect {str(plt).lower()} {le}B)"
                )
                self.enqueueCommandResult(
                    address,
                    seq,
                    ErciResultCode.INVALID_DATA_RECEIVED,
                    status_msg="Wrong frame length.",
                )
                return
        elif plt == PLT.MAXIMUM:
            if len(data) > le:
                ts_print(
                    f"STANDALONE: {color_string_fail('Long frame!')} ({len(data)}B vs. expect {str(plt).lower()} {le}B)"
                )
                self.enqueueCommandResult(
                    address,
                    seq,
                    ErciResultCode.INVALID_DATA_RECEIVED,
                    status_msg="Long frame.",
                )
                return
        else:
            raise ResponseError(
                f"STANDALONE: Unhandled expected packet length for cmd {str(ErciCmd(cmd))}. (L:{le} PLT:{str(plt)})"
            )

        if cmd == ErciCmd.SELECT_CONFIG:
            erebState = self.erebStates.setdefault(
                address,
                {
                    "state": ErciState.READY,
                    "config_id": ErciInvalid.CONFIG,
                    "ring_id": ErciInvalid.RING,
                    "antenna_id": ErciInvalid.ANTENNA,
                    "configmode_flag": 0,
                },
            )
            # TODO: Could do some FSM check here, if BUSY/RUNNING then return error
            erebState["state"] = ErciState.CONFIGURED

            erebState["config_id"] = data[ErciPosSelectConfig.CONFIG_ID]
            erebState["ring_id"] = data[ErciPosSelectConfig.RING_ID]
            erebState["antenna_id"] = data[ErciPosSelectConfig.ANTENNA_ID]
            self.enqueueCommandResult(
                address,
                seq,
                ErciResultCode.SUCCESS,
                status_msg=f"Selected config {erebState['config_id']} ring {erebState['ring_id']} antenna {erebState['antenna_id']}",
            )
        elif cmd == ErciCmd.SWITCH_RING:
            erebState = self.erebStates.setdefault(
                address,
                {
                    "state": ErciState.READY,
                    "config_id": ErciInvalid.CONFIG,
                    "ring_id": ErciInvalid.RING,
                    "antenna_id": ErciInvalid.ANTENNA,
                    "configmode_flag": 0,
                },
            )
            # TODO: Could do some FSM check here, if BUSY/RUNNING then return error
            erebState["ring_id"] = data[ErciPosSwitchRing.RING_ID]
            erebState["antenna_id"] = data[ErciPosSwitchRing.ANTENNA_ID]
            self.enqueueCommandResult(
                address,
                seq,
                ErciResultCode.SUCCESS,
                status_msg=f"Switched to ring {erebState['ring_id']} antenna {erebState['antenna_id']}",
            )
        elif cmd == ErciCmd.START:
            erebState = self.erebStates.setdefault(
                address,
                {
                    "state": ErciState.READY,
                    "config_id": ErciInvalid.CONFIG,
                    "ring_id": ErciInvalid.RING,
                    "antenna_id": ErciInvalid.ANTENNA,
                    "configmode_flag": 0,
                },
            )
            # TODO: Could do some FSM check here, if config/ring zero then return error
            erebState["state"] = ErciState.RUNNING
            self.enqueueCommandResult(
                address, seq, ErciResultCode.SUCCESS, status_msg="Started ring."
            )
        elif cmd == ErciCmd.STOP:
            erebState = self.erebStates.setdefault(
                address,
                {
                    "state": ErciState.READY,
                    "config_id": ErciInvalid.CONFIG,
                    "ring_id": ErciInvalid.RING,
                    "antenna_id": ErciInvalid.ANTENNA,
                    "configmode_flag": 0,
                },
            )
            # TODO: Could do some FSM check here, if not RUNNING then return error
            erebState["state"] = ErciState.READY
            self.enqueueCommandResult(
                address, seq, ErciResultCode.SUCCESS, status_msg="Stopped ring."
            )
        elif cmd == ErciCmd.STATE_QUERY:
            erebState = self.erebStates.setdefault(
                address,
                {
                    "state": ErciState.READY,
                    "config_id": ErciInvalid.CONFIG,
                    "ring_id": ErciInvalid.RING,
                    "antenna_id": ErciInvalid.ANTENNA,
                    "configmode_flag": 0,
                },
            )
            otherdata = bytearray()
            otherdata.append(erebState["state"])
            otherdata.append(erebState["config_id"])
            otherdata.append(erebState["ring_id"])
            otherdata.append(erebState["antenna_id"])
            self.enqueuePacket(
                self.createMessage(ErciCmd.STATE_RESPONSE, seq, otherdata), address
            )
        elif cmd == ErciCmd.DIAGNOSTIC_DESCRIPTION_QUERY:
            otherdata = bytearray(
                "RANDOM FILL FROM STANDALONE SERVER", encoding="utf-8"
            )
            otherdata.append(0)
            self.enqueuePacket(
                self.createMessage(
                    ErciCmd.DIAGNOSTIC_DESCRIPTION_RESPONSE, seq, otherdata
                ),
                address,
            )
        elif cmd == ErciCmd.SWITCH_ANTENNA:
            erebState = self.erebStates.setdefault(
                address,
                {
                    "state": ErciState.READY,
                    "config_id": ErciInvalid.CONFIG,
                    "ring_id": ErciInvalid.RING,
                    "antenna_id": ErciInvalid.ANTENNA,
                    "configmode_flag": 0,
                },
            )
            erebState["antenna_id"] = data[ErciPosSwitchAntenna.ANTENNA_ID]
            self.enqueueCommandResult(
                address,
                seq,
                ErciResultCode.SUCCESS,
                status_msg=f"Switched to antenna {erebState['antenna_id']}",
            )
        elif cmd == ErciCmd.SET_CONFIGMODE:
            erebState = self.erebStates.setdefault(
                address,
                {
                    "state": ErciState.READY,
                    "config_id": ErciInvalid.CONFIG,
                    "ring_id": ErciInvalid.RING,
                    "antenna_id": ErciInvalid.ANTENNA,
                    "configmode_flag": 0,
                },
            )
            erebState["configmode_flag"] = data[ErciPosSetConfigMode.CONFIG_MODE_FLAG]
            self.enqueueCommandResult(
                address,
                seq,
                ErciResultCode.SUCCESS,
                status_msg=f"Switched configmode flag to {erebState['configmode_flag']}",
            )
        elif cmd == ErciCmd.REBOOT:
            pass

        else:
            ts_print("STANDALONE: Not answering.")
