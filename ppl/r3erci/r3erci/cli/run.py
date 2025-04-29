import asyncio
from typing import Dict

from r3erci.client import ErciClient
from r3erci.constants import (
    ErciCmd,
    PORT,
)
from r3erci.exceptions import ErciException
from r3erci.util import ts_print


async def execute(args: Dict) -> None:
    timeout: int = args.timeout
    standalone: bool = args.standalone
    address: str = args.address
    ownaddress: str = args.ownaddress
    ownport: int = args.ownport
    command: str = args.command

    mac_address: str = args.mac_address if "mac_address" in args else None
    serial_number: str = args.serial_number if "serial_number" in args else None

    config_id: int = args.config_id if "config_id" in args else None
    ring_id: int = args.ring_id if "ring_id" in args else None
    antenna_id: int = args.antenna_id if "antenna_id" in args else None

    configmode_flag: int = args.configmode_flag if "configmode_flag" in args else None

    try:
        client = ErciClient(
            ownaddress=ownaddress,
            ownport=ownport,
            timeout=timeout,
            standalone=standalone,
        )
        if command == "config":
            assert config_id is not None, "Must specify config_id"
            assert ring_id is not None, "Must specify ring_id"
            assert antenna_id is not None, "Must specify antenna_id"
            await client.send_command(
                address,
                ErciCmd.SELECT_CONFIG,
                config_id=config_id,
                ring_id=ring_id,
                antenna_id=antenna_id,
            )

        elif command == "ring":
            assert ring_id is not None, "Must specify ring_id"
            assert antenna_id is not None, "Must specify antenna_id"
            await client.send_command(
                address, ErciCmd.SWITCH_RING, ring_id=ring_id, antenna_id=antenna_id
            )

        elif command == "start":
            await client.send_command(address, ErciCmd.START)

        elif command == "stop":
            await client.send_command(address, ErciCmd.STOP)

        elif command == "state":
            await client.send_command(address, ErciCmd.STATE_QUERY)

        elif command == "diagdesc":
            await client.send_command(address, ErciCmd.DIAGNOSTIC_DESCRIPTION_QUERY)

        elif command == "antenna":
            assert antenna_id is not None, "Must specify antenna_id"
            await client.send_command(
                address, ErciCmd.SWITCH_ANTENNA, antenna_id=antenna_id
            )

        elif command == "configmode":
            assert configmode_flag is not None, "Must specify configmode flag"
            await client.send_command(
                address, ErciCmd.SET_CONFIGMODE, configmode_flag=configmode_flag
            )

        elif command == "passportquery":
            assert mac_address is not None, "Must specify mac_address"
            assert serial_number is not None, "Must specify serial_number"
            await client.send_command(
                address,
                ErciCmd.PASSPORT_QUERY,
                mac_address=mac_address,
                serial_number=serial_number,
            )

        elif command == "reboot":
            await client.send_command(address, ErciCmd.REBOOT)

        elif command == "csi":
            await client.send_command(address, ErciCmd.GET_CSI_QUERY)

        else:
            ts_print(f"Unknown command '{command}'!")
    except ValueError as e:
        ts_print(f"Raised error: {e}")
    except ErciException as e:
        ts_print(f"Raised error: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Testing client simulating the PLC part of ERCI."
    )
    parser.add_argument("address", help="The IP/FQDN of the EREB")
    parser.add_argument(
        "-s",
        "--standalone",
        action="store_true",
        default=False,
        help="Simulates the EREBs",
    )
    parser.add_argument(
        "-t", "--timeout", type=int, default=10, help="Time to wait for response"
    )
    parser.add_argument(
        "-o",
        "--ownaddress",
        type=str,
        default="0.0.0.0",
        help="The interface to be used",
    )
    parser.add_argument(
        "-p",
        "--ownport",
        type=str,
        default=PORT,
        help="The port to be used",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    subparser_select_config = subparsers.add_parser(
        "config", help="Sends command SELECT CONFIG"
    )
    subparser_select_config.add_argument(
        "config_id", type=int, help="The ID of the configuration to be selected"
    )
    subparser_select_config.add_argument(
        "ring_id", type=int, help="The ID of the ring to switch to"
    )
    subparser_select_config.add_argument(
        "antenna_id", type=int, help="The ID of the antenna to switch to"
    )

    subparser_switch_ring = subparsers.add_parser(
        "ring", help="Sends command SWITCH RING"
    )
    subparser_switch_ring.add_argument(
        "ring_id", type=int, help="The ID of the ring to switch to"
    )
    subparser_switch_ring.add_argument(
        "antenna_id", type=int, help="The ID of the antenna to switch to"
    )

    subparsers.add_parser("start", help="Sends command START")

    subparsers.add_parser("stop", help="Sends command STOP")

    subparsers.add_parser("state", help="Sends command QUERY STATE")

    subparsers.add_parser("diagdesc", help="Sends command DIAGNOSTIC DESCRIPTION QUERY")

    subparser_switch_antenna = subparsers.add_parser(
        "antenna", help="Sends command SWITCH ANTENNA"
    )
    subparser_switch_antenna.add_argument(
        "antenna_id", type=int, help="The ID of the antenna to switch to"
    )

    subparser_configmode = subparsers.add_parser(
        "configmode", help="Sends command SET CONFIGMODE"
    )
    subparser_configmode.add_argument(
        "configmode_flag", type=int, help="The value of the configmode flag to be set"
    )

    subparser_passport_query = subparsers.add_parser(
        "passportquery", help="Sends command PASSPORT QUERY"
    )
    subparser_passport_query.add_argument(
        "mac_address",
        type=str,
        help="The MAC address to be queried in hex without 0x (optionally separated by colons): e.g. AABBCCDDEEFF or AA:BB:CC:DD:EE:FF",
    )
    subparser_passport_query.add_argument(
        "serial_number", type=str, help="The serial number to be queried"
    )

    subparsers.add_parser("reboot", help="Sends command REBOOT")

    subparsers.add_parser("csi", help="Sends command GET_CSI")

    args = parser.parse_args()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(execute(args))


if __name__ == "__main__":
    main()
