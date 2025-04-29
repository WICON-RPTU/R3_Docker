import socket

from r3erci.constants import (
    PORT,
    PROTOCOL_VERSION,
    RESERVED_VALUE,
    ErciCmd,
    ErciInvalid,
    ErciPosCmdRes,
    ErciPosHeader,
    ErciPosSelectConfig,
    ErciPosStateRes,
    ErciPosSwitchRing,
    ErciPosSwitchAntenna,
    ErciPosSetConfigMode,
    ErciResultCode,
    ErciState,
    GetPacketLength,
)
from r3erci.constants import PacketLengthType as PLT
from r3erci.util import color_string_fail, colors


class SimulateEreb:
    def __init__(self):
        self.port = PORT

        self.state = ErciState.READY
        self.config_id = ErciInvalid.CONFIG
        self.ring_id = ErciInvalid.RING
        self.antenna_id = ErciInvalid.ANTENNA

        self.configmode_flag = 0

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.sock.bind(("0.0.0.0", self.port))

    def run(self):

        try:
            while True:
                data, addr = self.sock.recvfrom(100)
                print("")
                print(f"Request from {addr[0]}:{addr[1]}: {data}")

                le, plt = GetPacketLength(None)
                if len(data) < le:
                    print(
                        f"Response from {addr[0]}: {color_string_fail('Short frame!')} ({len(data)}B vs. expect {str(plt).lower} {le}B)"
                    )
                    continue

                if data[ErciPosHeader.RESERVED] != RESERVED_VALUE:
                    print(f"  Reserved field not {RESERVED_VALUE}!")

                if data[ErciPosHeader.PROTOCOL_VERSION] != PROTOCOL_VERSION:
                    print(f"  Version field not {PROTOCOL_VERSION}!")

                seq = data[ErciPosHeader.SEQUENCE]
                print(f"  Sequence Number: {seq}")

                cmd = data[ErciPosHeader.COMMAND]
                print(f"  Type: {str(ErciCmd(cmd))}")

                if cmd == ErciCmd.INVALID:
                    print("  Should not be received!")
                    continue

                le, plt = GetPacketLength(cmd)
                if plt == PLT.MINIMUM:
                    if len(data) < le:
                        print(
                            f"Response from {addr[0]}: {color_string_fail('Short frame!')} ({len(data)}B vs. expect {str(plt).lower()} {le}B)"
                        )
                        continue
                elif plt == PLT.EXACT:
                    if len(data) != le:
                        print(
                            f"Response from {addr[0]}: {color_string_fail('Wrong frame length!')} ({len(data)}B vs. expect {str(plt).lower()} {le}B)"
                        )
                        continue
                elif plt == PLT.MAXIMUM:
                    if len(data) > le:
                        print(
                            f"Response from {addr[0]}: {color_string_fail('Long frame!')} ({len(data)}B vs. expect {str(plt).lower()} {le}B)"
                        )
                        continue
                else:
                    print(
                        f"Unhandled expected packet length for cmd {str(ErciCmd(cmd))}. (L:{le} PLT:{str(plt)})"
                    )
                    continue

                if cmd == ErciCmd.SELECT_CONFIG:

                    if (self.state != ErciState.READY) and (
                        self.state != ErciState.CONFIGURED
                    ):
                        self.send_command_result_wrong_state(addr, seq)
                        continue

                    self.state = ErciState.CONFIGURED
                    self.config_id = data[ErciPosSelectConfig.CONFIG_ID]
                    self.ring_id = data[ErciPosSelectConfig.RING_ID]
                    self.antenna_id = data[ErciPosSelectConfig.ANTENNA_ID]

                    print(
                        f"    Config ID: {self.config_id} Ring ID: {self.ring_id} Antenna ID: {self.antenna_id}"
                    )
                    self.send_command_result(
                        addr,
                        seq,
                        ErciResultCode.SUCCESS,
                        f"Selected config {self.config_id} ring {self.ring_id} antenna {self.antenna_id}",
                    )

                elif cmd == ErciCmd.SWITCH_RING:

                    if self.state != ErciState.RUNNING:
                        self.send_command_result_wrong_state(addr, seq)
                        continue

                    self.ring_id = data[ErciPosSwitchRing.RING_ID]
                    self.antenna_id = data[ErciPosSwitchRing.ANTENNA_ID]

                    print(f"    Ring ID: {self.ring_id} Antenna ID: {self.antenna_id}")
                    self.send_command_result(
                        addr,
                        seq,
                        ErciResultCode.SUCCESS,
                        f"Switched to ring {self.ring_id} antenna {self.antenna_id}",
                    )

                elif cmd == ErciCmd.START:

                    if self.state != ErciState.CONFIGURED:
                        self.send_command_result_wrong_state(addr, seq)
                        continue

                    self.state = ErciState.RUNNING
                    self.send_command_result(
                        addr, seq, ErciResultCode.SUCCESS, "Started ring."
                    )

                elif cmd == ErciCmd.STOP:

                    if self.state != ErciState.RUNNING:
                        self.send_command_result_wrong_state(addr, seq)
                        continue

                    self.state = ErciState.READY
                    self.config_id = ErciInvalid.CONFIG
                    self.ring_id = ErciInvalid.RING
                    self.antenna_id = ErciInvalid.ANTENNA
                    self.send_command_result(
                        addr, seq, ErciResultCode.SUCCESS, "Stopped ring."
                    )

                elif cmd == ErciCmd.COMMAND_RESULT:
                    print(f"  Should not be received!")
                    print(f"    Status Code: {data[ErciPosCmdRes.CODE]}")
                    if data[-1] != 0x0:
                        print("    The Status Message is not NULL terminated!")
                        continue
                    print(f"    Status Message: {data[ErciPosCmdRes.MSG_START :]}")

                elif cmd == ErciCmd.STATE_QUERY:
                    self.send_state_response(
                        addr,
                        seq,
                        self.state,
                        self.config_id,
                        self.ring_id,
                        self.antenna_id,
                    )

                elif cmd == ErciCmd.STATE_RESPONSE:
                    print(f"  Should not be received!")
                    print(f"    State:      {data[ErciPosStateRes.STATE]}")
                    print(f"    Config ID:  {data[ErciPosStateRes.CONFIG_ID]}")
                    print(f"    Ring ID:    {data[ErciPosStateRes.RING_ID]}")
                    print(f"    Antenna ID: {data[ErciPosStateRes.ANTENNA_ID]}")

                elif cmd == ErciCmd.DIAGNOSTIC_DESCRIPTION_QUERY:
                    self.send_diag_desc_reply(
                        addr,
                        seq,
                    )

                elif cmd == ErciCmd.SWITCH_ANTENNA:

                    if self.state != ErciState.RUNNING:
                        self.send_command_result_wrong_state(addr, seq)
                        continue

                    self.antenna_id = data[ErciPosSwitchAntenna.ANTENNA_ID]

                    print(f"    Antenna ID: {self.antenna_id}")
                    self.send_command_result(
                        addr,
                        seq,
                        ErciResultCode.SUCCESS,
                        f"Switched to antenna {self.antenna_id}",
                    )

                elif cmd == ErciCmd.SET_CONFIGMODE:
                    self.configmode_flag = data[ErciPosSetConfigMode.CONFIG_MODE_FLAG]

                    print(f"    Configmode Flag: {self.configmode_flag}")
                    self.send_command_result(
                        addr,
                        seq,
                        ErciResultCode.SUCCESS,
                        f"Switched configmode flag to {self.configmode_flag}",
                    )

                elif cmd == ErciCmd.REBOOT:
                    print(f"   REBOOOOOOOOT")
                    self.send_command_result(
                        addr, seq, ErciResultCode.SUCCESS, f"Rebooting..."
                    )

                elif cmd == ErciCmd.GET_CSI_QUERY:
                    print(f"    CSI data")
                    self.send_csi_resonse(
                        addr, seq, ErciResultCode.SUCCESS #ErciResultCode.WRONG_STATE #
                    )

                else:
                    print("  UNHANDLED PACKET!")
                    continue

        except KeyboardInterrupt:
            print("")

    def get_erci_header(self, msg_type, seq):
        header = bytearray()
        header.append(RESERVED_VALUE)
        header.append(PROTOCOL_VERSION)
        header.append(int(msg_type))
        header.append(seq)
        return header

    def send_command_result_wrong_state(self, dst, seq):
        self.send_command_result(
            dst,
            seq,
            ErciResultCode.WRONG_STATE,
            f"Not allowed in state {str(self.state)}",
        )

    def send_command_result(self, dst, seq, status_code, status_msg):
        if status_code < 0 or status_code > 255:
            print("Argument status_code needs to be in the range 0..255!")
            return

        print(
            f"Sending Command Result with status_code={status_code} to {dst[0]}:{dst[1]}..."
        )
        data = self.get_erci_header(ErciCmd.COMMAND_RESULT, seq)

        data.append(status_code)
        data.extend(status_msg.encode())
        data.append(0x0)

        self.sock.sendto(data, dst)

    def send_state_response(self, dst, seq, state, config_id, ring_id, antenna_id):
        if state < 0 or state > 255:
            print("Argument state needs to be in the range 0..255!")
            return
        if config_id < 0 or config_id > 255:
            print("Argument config_id needs to be in the range 0..255!")
            return
        if ring_id < 0 or ring_id > 255:
            print("Argument ring_id needs to be in the range 0..255!")
            return
        if antenna_id < 0 or antenna_id > 255:
            print("Argument antenna_id needs to be in the range 0..255!")
            return

        print(
            f"Sending State Response with state={state} config_id={config_id} ring_id={ring_id} antenna_id={antenna_id} to {dst[0]}:{dst[1]}..."
        )

        data = self.get_erci_header(ErciCmd.STATE_RESPONSE, seq)

        data.append(state)
        data.append(config_id)
        data.append(ring_id)
        data.append(antenna_id)

        self.sock.sendto(data, dst)

    def send_diag_desc_reply(self, dst, seq):

        data = self.get_erci_header(ErciCmd.DIAGNOSTIC_DESCRIPTION_RESPONSE, seq)

        msg = f"Config ID: {self.config_id} Ring ID: {self.ring_id} Antenna ID: {self.antenna_id} Configmode Flag: {self.configmode_flag}"

        data += bytearray(msg, encoding="utf-8")

        data.append(0x0)

        self.sock.sendto(data, dst)

    def send_csi_resonse(self, dst, seq, status_code):
        data = self.get_erci_header(ErciCmd.GET_CSI_RESPONSE, seq)
        data.append(status_code)

        if (status_code == ErciResultCode.SUCCESS):
            ownId = 14
            staId_2 = 29
            staId_3 = 99
            staId_e = 0
            data.extend(ownId.to_bytes(2, 'big'))
            data.extend(staId_2.to_bytes(2, 'big'))
            data.extend(staId_3.to_bytes(2, 'big'))
            for i in range(17):
                data.extend(staId_e.to_bytes(2, 'big'))
            for i in range(190):
                data.extend(staId_e.to_bytes(4, 'big'))

        self.sock.sendto(data, dst)


def main():
    ereb = SimulateEreb()

    ereb.run()


if __name__ == "__main__":
    main()
