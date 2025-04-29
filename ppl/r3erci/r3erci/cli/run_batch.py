import asyncio
import socket
from ipaddress import ip_address
from typing import List

from r3erci.client import ErciClient
from r3erci.constants import ErciCmd
from r3erci.exceptions import ErciException
from r3erci.util import ts_print

command_lut = {
    "start": ErciCmd.START,
    "stop": ErciCmd.STOP,
    "state": ErciCmd.STATE_QUERY,
    "diagdesc": ErciCmd.DIAGNOSTIC_DESCRIPTION_QUERY,
    "reboot": ErciCmd.REBOOT,
}


async def exec(address: str, command: ErciCmd) -> None:
    client = ErciClient()
    try:
        await client.send_command(address, command)
    except ValueError as e:
        ts_print(f"Raised error: {e}")
    except ErciException as e:
        ts_print(f"Raised error: {e}")


async def async_main(ips: List, cmd: ErciCmd) -> None:
    jobs = []
    for ip in ips:
        jobs.append(exec(ip, cmd))
    await asyncio.gather(*jobs)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Helper to run a batch of ERCI commands against a list of inputs."
    )
    parser.add_argument("command", choices=command_lut.keys())
    parser.add_argument("iplist", type=argparse.FileType("r", encoding="UTF-8"))

    args = parser.parse_args()

    ips: List[str] = []
    for ip_line in args.iplist.read().splitlines():
        if not ip_line or ip_line[0] == "#":
            continue
        try:
            ip_address(ip_line)
        except ValueError:
            try:
                ip_address(socket.gethostbyname(ip_line))
            except (socket.gaierror, ValueError) as e:
                print(f"Skipping invalid IP/FQDN: {ip_line}: {e}")
                continue
        ips.append(ip_line)

    cmd = command_lut[args.command]

    loop = asyncio.get_event_loop()
    loop.run_until_complete(async_main(ips, cmd))
    args.iplist.close()


if __name__ == "__main__":
    main()
