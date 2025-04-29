import asyncio
from ipaddress import IPv4Address, ip_address
from typing import Optional, Tuple
from struct import unpack

from r3erci.constants import (
    PORT,
    PROTOCOL_VERSION,
    RESERVED_VALUE,
    MAC_ADDRESS_LENGTH,
    SERIAL_NUMBER_LENGTH,
    STAID_LENGTH,
    CSI_LENGTH,
    ErciCmd,
    ErciPosCmdRes,
    ErciPosDiagdesc,
    ErciPosHeader,
    ErciPosStateRes,
    ErciPosPassportQueryResponse,
    ErciPosCsiGetResponse,
    ErciResultCode,
    ErciState,
    GetStateStringColor,
    GetPacketLength,
)
from r3erci.constants import PacketLengthType as PLT
from r3erci.exceptions import ResourceLocked, ResponseError, TimeoutError
from r3erci.standaloneServer import StandaloneServer
from r3erci.udpServer import UdpServer
from r3erci.util import (
    ts_print,
    color_string,
    color_string_fail,
    color_string_success,
    colors,
)


class ErciQuery:
    def __init__(self, udpServer, timeout):
        self.udpServer = udpServer
        self.timeout = timeout
        self.response = None

    @staticmethod
    def _wait_for(event: asyncio.Event, timeout: float):
        return asyncio.wait_for(event.wait(), timeout)

    async def execute(
        self, data: bytes, address: IPv4Address, responseCmd=None, seq=None
    ) -> Tuple[bytes, Tuple[str, int]]:
        # logger.debug("Executing {}: {}", self.address, repr(self.query))
        queryEvent = asyncio.Event()

        async def responseHandler(
            command: ErciCmd, sequence: int, message: bytes, address: Tuple[str, int]
        ) -> bool:
            # logger.debug("GotResp: {}:  {}", address[0], repr(message))
            self.response = message
            self.rx_address = address
            queryEvent.set()
            return True

        with self.udpServer.subscriberFilterContext(
            responseHandler,
            filterCmd=responseCmd if responseCmd else None,
            filterSeq=seq if seq else None,
            filterAddr=str(address),
        ):
            self.udpServer.sendPacket(data, address, PORT)
            try:
                await self._wait_for(queryEvent, self.timeout)
                queryEvent.clear()
            except asyncio.TimeoutError:
                raise TimeoutError(f"{address}: No response in {self.timeout} seconds.")
        assert self.response is not None
        return self.response, self.rx_address


class ErciClient:
    seqno = 0

    def __init__(
        self,
        ownaddress: str = "0.0.0.0",
        ownport: int = PORT,
        timeout: int = 3,
        standalone: bool = False,
        disablePrints: bool = False,
    ):
        self.timeout = timeout
        self.disablePrints = disablePrints
        self.queryLock = asyncio.Lock()
        if standalone:
            self.udpServer = StandaloneServer()
        else:
            self.udpServer = UdpServer(ownaddress, ownport)

    def _handle_response(self, rxdata: bytes, addr: Tuple[str, int]):
        le, plt = GetPacketLength(None)
        if len(rxdata) < le:
            raise ResponseError(
                f"Response from {addr[0]}: {color_string_fail('Short frame!')} ({len(rxdata)}B vs. expect {str(plt).lower} {le}B)"
            )

        if rxdata[ErciPosHeader.RESERVED] != RESERVED_VALUE:
            raise ResponseError(
                f"Response from {addr[0]}: {color_string_fail(f'Reserved field not {RESERVED_VALUE} but {rxdata[ErciPosHeader.RESERVED]}!')}"
            )

        if rxdata[ErciPosHeader.PROTOCOL_VERSION] != PROTOCOL_VERSION:
            raise ResponseError(
                f"Response from {addr[0]}: {color_string_fail(f'Version field not 0x{PROTOCOL_VERSION} but {rxdata[ErciPosHeader.PROTOCOL_VERSION]}!')}"
            )

        rx_seqno = rxdata[ErciPosHeader.SEQUENCE]

        if rx_seqno != self.seqno:
            raise ResponseError(
                f"Response from {addr[0]}: {color_string_fail(f'Mismatching sequence number: {self.seqno} -> {rx_seqno}!')}"
            )

        try:
            msg_type = ErciCmd(rxdata[ErciPosHeader.COMMAND])
        except ValueError:
            raise ResponseError(
                f"Response from {addr[0]}: {color_string_fail(f'Response Type: unknown {rxdata[ErciPosHeader.COMMAND]}!')}"
            )

        if (
            msg_type == ErciCmd.INVALID
            or msg_type == ErciCmd.SELECT_CONFIG
            or msg_type == ErciCmd.SWITCH_RING
            or msg_type == ErciCmd.START
            or msg_type == ErciCmd.STOP
            or msg_type == ErciCmd.STATE_QUERY
            or msg_type == ErciCmd.DIAGNOSTIC_DESCRIPTION_QUERY
            or msg_type == ErciCmd.PASSPORT_QUERY
            or msg_type == ErciCmd.REBOOT
            or msg_type == ErciCmd.GET_CSI_QUERY
        ):
            raise ResponseError(
                f"Response {color_string_fail(str(ErciCmd(msg_type)))} from {addr[0]} should not have been received."
            )

        le, plt = GetPacketLength(msg_type)
        if plt == PLT.MINIMUM:
            if len(rxdata) < le:
                raise ResponseError(
                    f"Response from {addr[0]}: {color_string_fail('Short frame!')} ({len(rxdata)}B vs. expect {str(plt).lower()} {le}B)"
                )
        elif plt == PLT.EXACT:
            if len(rxdata) != le:
                raise ResponseError(
                    f"Response from {addr[0]}:{color_string_fail('Wrong frame length!')} ({len(rxdata)}B vs. expect {str(plt).lower()} {le}B)"
                )
        elif plt == PLT.MAXIMUM:
            if len(rxdata) > le:
                raise ResponseError(
                    f"Response from {addr[0]}: {color_string_fail('Long frame!')} ({len(rxdata)}B vs. expect {str(plt).lower()} {le}B)"
                )
        else:
            raise ResponseError(
                f"Unhandled expected packet length for cmd {str(ErciCmd(msg_type))}. (L:{le} PLT:{str(plt)})"
            )

        if msg_type == ErciCmd.COMMAND_RESULT:
            if rxdata[-1] != 0x0:
                raise ResponseError(
                    f"Response from {addr[0]}: COMMAND_RESULT {color_string_fail('The Status Message is not NULL terminated!')}"
                )

            r = {
                "type": msg_type,
                "success": None,
                "status_msg": None,
            }

            r["status_msg"] = rxdata[ErciPosCmdRes.MSG_START :].decode()
            if rxdata[ErciPosCmdRes.CODE] != ErciResultCode.SUCCESS:
                self._print(
                    f"Response from {addr[0]}: COMMAND_RESULT {color_string_fail('FAILED')} - \"{r['status_msg']}\""
                )
                r["success"] = False
            else:
                self._print(
                    f"Response from { addr[0]}: COMMAND_RESULT {color_string_success('SUCCESS')} - \"{r['status_msg']}\""
                )
                r["success"] = True
            return r

        elif msg_type == ErciCmd.STATE_RESPONSE:
            r = {
                "type": msg_type,
                "config_id": rxdata[ErciPosStateRes.CONFIG_ID],
                "ring_id": rxdata[ErciPosStateRes.RING_ID],
                "antenna_id": rxdata[ErciPosStateRes.ANTENNA_ID],
                "state": None,
            }

            try:
                state = ErciState(rxdata[ErciPosStateRes.STATE])
            except ValueError:
                raise ResponseError(
                    f"Response from {addr[0]}: {color_string_fail(f'Response state: unknown {rxdata[ErciPosStateRes.STATE]}!')}"
                )

            self._print(
                f"Response from {addr[0]}: STATE_RESPONSE State: {color_string(str(state), GetStateStringColor(state))}"
            )
            r["state"] = state

            self._print(
                f"Config ID: {rxdata[ErciPosStateRes.CONFIG_ID]}"
                f", Ring ID: {rxdata[ErciPosStateRes.RING_ID]}"
                f", Antenna ID: {rxdata[ErciPosStateRes.ANTENNA_ID]}"
            )

            return r

        elif msg_type == ErciCmd.DIAGNOSTIC_DESCRIPTION_RESPONSE:
            if rxdata[-1] != 0x0:
                raise ResponseError(
                    f"Response from {addr[0]}: DIAGNOSTIC_DESCRIPTION_RESPONSE {color_string_fail('The Description is not NULL terminated!')}"
                )

            r = {
                "type": msg_type,
                "diagnostic_description": rxdata[ErciPosDiagdesc.MSG_START :].decode(
                    encoding="UTF-8", errors="backslashreplace"
                ),
            }
            self._print(
                f"Response from {addr[0]}: DIAGNOSTIC_DESCRIPTION_RESPONSE: {r['diagnostic_description']}"
            )
            return r

        elif msg_type == ErciCmd.PASSPORT_QUERY_RESPONSE:
            pos_mac = ErciPosPassportQueryResponse.MAC_ADDRESS
            pos_serial = ErciPosPassportQueryResponse.SERIAL_NUMBER
            r = {
                "type": msg_type,
                "status": ErciResultCode(rxdata[ErciPosPassportQueryResponse.CODE]),
                "mac_address": rxdata[pos_mac : pos_mac + MAC_ADDRESS_LENGTH],
                "serial_number": rxdata[pos_serial : pos_serial + SERIAL_NUMBER_LENGTH],
            }

            mac_string = "mac_address=" + ":".join(f"{x:02X}" for x in r["mac_address"])
            serial_string = "serial_number=" + "".join(
                f"{x:c}" for x in r["serial_number"]
            )
            if r["status"] != ErciResultCode.SUCCESS:
                self._print(
                    f"Response from {addr[0]}: PASSPORT_QUERY_RESPONSE {color_string_fail('FAILED')} ({r['status']}) - {mac_string} {serial_string}"
                )
                r["success"] = False
            else:
                self._print(
                    f"Response from { addr[0]}: PASSPORT_QUERY_RESPONSE {color_string_success('SUCCESS')} - {mac_string} {serial_string}"
                )
                r["success"] = True

            return r
        
        elif msg_type == ErciCmd.GET_CSI_RESPONSE:
            status = ErciResultCode(rxdata[ErciPosCsiGetResponse.CODE])
            r = {
                "type": msg_type,
                "status": status,
            }
            if status == ErciResultCode.SUCCESS:
                sta = 20
                sta_array = rxdata[ErciPosCsiGetResponse.STA_ID : ErciPosCsiGetResponse.STA_ID + 20*STAID_LENGTH]
                r["ownId"] = unpack('!'+'H'*(len(sta_array)//2), sta_array)[0]
                r["staIds"] = unpack('!'+'H'*(len(sta_array)//2), sta_array)
                self._print(
                    f"Response from { addr[0]}: GET_CSI_RESPONSE {color_string_success('SUCCESS')} for Station {r['ownId']}"
                    f"\nAll Stations: [{', '.join(str(i) for i in r['staIds'])}]"
                )
                data = unpack('!'+'I'*(sta*(sta-1)//2), rxdata[ErciPosCsiGetResponse.CSI : ErciPosCsiGetResponse.CSI + (sta*(sta-1)*2)])
                data = [(x / 16777216) for x in data]
                offset = 0
                for i_row in range(sta):
                    if i_row == 0:
                        print(" \t", ("\t").join(["%.2d" % i for i in range(1, sta+1)]))
                    print("{:02d}\t".format(i_row+1), " \t"*(i_row), "X", ("\t{:.2f}"*(sta-i_row-1)).format(*data[offset:offset+sta-i_row-1]))
                    offset += sta-i_row-1
                r["success"] = True
            elif status == ErciResultCode.WRONG_STATE:
                self._print(
                    f"Response from {addr[0]}: GET_CSI_RESPONSE {color_string_fail('FAILED')} ({status}) - EREB must be deployed and in state RUNNING"
                )
                r["success"] = False
            else:
                self._print(
                    f"Response from {addr[0]}: GET_CSI_RESPONSE {color_string_fail('FAILED')} ({status})"
                )
                r["success"] = False

        else:
            raise ResponseError(
                f"Response from {addr[0]}: {color_string_fail(f'Unhandeled response type ({msg_type})')}"
            )

    async def _send_command_and_handle_response(
        self, txdata: bytes, address: IPv4Address
    ) -> dict:
        response, rx_address = await ErciQuery(self.udpServer, self.timeout).execute(
            txdata, address, seq=self.seqno
        )
        result = self._handle_response(response, rx_address)
        return result

    def _create_msg(
        self,
        msg_type: ErciCmd,
        config_id: Optional[int],
        ring_id: Optional[int],
        antenna_id: Optional[int],
        configmode_flag: Optional[int],
        mac_address: Optional[bytearray],
        serial_number: Optional[bytearray],
    ):
        data = bytearray()
        data.append(RESERVED_VALUE)
        data.append(PROTOCOL_VERSION)
        data.append(int(msg_type))
        self.seqno = self.seqno + 1
        if self.seqno > 255:
            self.seqno = 0
        data.append(self.seqno)

        if config_id is not None:
            data.append(config_id)
        if ring_id is not None:
            data.append(ring_id)
        if antenna_id is not None:
            data.append(antenna_id)

        if configmode_flag is not None:
            data.append(configmode_flag)

        if mac_address is not None:
            data.extend(mac_address)
        if serial_number is not None:
            data.extend(serial_number)

        return data

    async def send_command(
        self,
        address: str,
        command: ErciCmd,
        config_id: int = None,
        ring_id: int = None,
        antenna_id: int = None,
        configmode_flag: int = None,
        mac_address: str = None,
        serial_number: str = None,
    ) -> dict:
        ip = ip_address(address)

        if config_id is not None:
            assert ring_id is not None
            assert antenna_id is not None
            if (config_id < 1) or (config_id > 255):
                raise ValueError("Argument config_id needs to be in the range 1..255!")
        if ring_id is not None:
            assert antenna_id is not None
            if (ring_id < 1) or (ring_id > 255):
                raise ValueError("Argument ring_id needs to be in the range 1..255!")
        if antenna_id is not None:
            if (antenna_id < 1) or (antenna_id > 255):
                raise ValueError("Argument antenna_id needs to be in the range 1..255!")

        if configmode_flag is not None:
            if (configmode_flag != 0) and (configmode_flag != 1):
                raise ValueError("Argument configmode_flag needs to be 0 or 1!")

        if mac_address is not None:
            assert serial_number is not None

            # convert standard colon notation of MACs to byte array
            if (
                len(mac_address) == MAC_ADDRESS_LENGTH * 2 + MAC_ADDRESS_LENGTH - 1
            ):  # 6 Bytes with 2 chars plus 5 colons in between
                tokens = mac_address.split(":")
                if len(tokens) != 6:
                    raise ValueError(
                        "Argument mac_address must be 6 hex bytes (optionally separated by colons): AABBCCDDEEFF or AA:BB:CC:DD:EE:FF"
                    )
            elif (
                len(mac_address) == MAC_ADDRESS_LENGTH * 2
            ):  # 6 Bytes with 2 chars without separators
                tokens = list(
                    mac_address[i : i + 2] for i in range(0, len(mac_address), 2)
                )
            else:
                raise ValueError(
                    "Argument mac_address must be 6 hex bytes (optionally separated by colons): AABBCCDDEEFF or AA:BB:CC:DD:EE:FF"
                )

            mac_address = bytearray()
            for token in tokens:
                mac_address.extend(bytes.fromhex(token))
        if serial_number is not None:
            assert mac_address is not None

            serial_number = bytearray(serial_number, "ascii")

            # append 0x00 in case provided string is not yet full length
            if len(serial_number) < SERIAL_NUMBER_LENGTH:
                serial_number.extend(
                    b"\0" * (SERIAL_NUMBER_LENGTH - len(serial_number))
                )

            if len(serial_number) != SERIAL_NUMBER_LENGTH:
                raise ValueError(
                    f"Argument serial_number must be length {SERIAL_NUMBER_LENGTH} but is {len(serial_number)}!"
                )

        if self.queryLock.locked():
            raise ResourceLocked("Another ERCI query is currently active.")

        params = " with "
        if configmode_flag is not None:
            params += f"configmode_flag={configmode_flag}"
        elif (mac_address is not None) and (serial_number is not None):
            params += "mac_address=" + ":".join(f"{x:02X}" for x in mac_address)
            params += " serial_number=" + "".join(f"{x:c}" for x in serial_number)
        else:
            params += f"ring_id={ring_id}" if ring_id else ""
            params += f", config_id={config_id}" if config_id else ""
            params += f", antenna_id={antenna_id}" if antenna_id else ""

        self._print(f"Sending command {str(command)}{params} to {address}:{PORT}...")

        async with self.queryLock:
            data = self._create_msg(
                command,
                config_id,
                ring_id,
                antenna_id,
                configmode_flag,
                mac_address,
                serial_number,
            )
            return await self._send_command_and_handle_response(data, ip)

    def _print(self, msg):
        if self.disablePrints == False:
            ts_print(msg)
