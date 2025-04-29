import asyncio
import json
import os
import ppl.packetDefinitions as pd
from ppl.client import PplClient
from ppl.constants import SERVERPORT
from ppl.exceptions import PplException
from ppl.util import ts_print, enableLog
from ppl.enums import ConfigStorageMode


async def execute(args: dict):

    timeout: int = args.timeout
    ownaddress: str = args.ownaddress
    ownport: int = args.ownport

    command: str = args.command

    enableLogging: bool = args.enable_logging if "enable_logging" in args else False

    address: int = args.ip if "ip" in args else None
    jsonPath: str = args.input_file if "input_file" in args else None

    force_unpair: int = args.force_unpair if "force_unpair" in args else None
    skip_test: int = args.skip_test if "skip_test" in args else None
    skip_clear: int = args.skip_clear if "skip_clear" in args else None
    
    output_file: int = args.output_file if "output_file" in args else None
    force_write: int = args.force_write if "force_write" in args else False

    if output_file is not None:
        if not _outputPathValid(output_file, force_write):
            return

    try:
        client = PplClient(
            ownaddress=ownaddress,
            ownport=ownport,
            timeout=timeout
        )
        if enableLogging == True:
            global enableLog
            enableLog(True)
        if command == "validate":
            client.runCmdValidateJson(jsonPath)
        elif command == "test":
            await client.runCmdTest(address, jsonPath, force_unpair)
        elif command == "clear":
            await client.runCmdClear(address, force_unpair)
        elif command == "configure":
            await client.runCmdConfigure(address, force_unpair, skip_test, skip_clear, jsonPath)
        else:
            ts_print(f"Unknown command '{command}'!")
            
    except ValueError as e:
        ts_print(f"Raised error: {e}")
    except PplException as e:
        ts_print(f"Raised error: {e}")
    finally:
        print(client.output)
        if len(client.output['response']) > 0:
            if command == "configure" and output_file is not None:
                _writeJson(output_file, client.output, force_write)

def _outputPathValid(filePath, force_write):
    if os.path.isfile(filePath) and not force_write:
        print(f"File {filePath} already exists. Use '--force_write' to override file or choose another file")
        return False
    return True

def _writeJson(filePath, output, force_write):
    if _outputPathValid(filePath, force_write):
        with open(filePath, 'w') as file:
            json.dump(output, file, indent=4)
    else:
        print("Couldn't write output file")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Client for pyrtmf protocal library"
    )

    parser.add_argument(
        "-t", "--timeout", type=int, default=3, help="Time to wait for response"
    )
    parser.add_argument(
        "-a",
        "--ownaddress",
        type=str,
        default="0.0.0.0",
        help="The interface to be used",
    )
    parser.add_argument(
        "-p",
        "--ownport",
        type=str,
        default=SERVERPORT,
        help="The port to be used"
    )
    parser.add_argument(
        "-l",
        "--enable_logging", action='store_true', required=False, help="Enable extended logging in the console"
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # Validate
    subparser_validate = subparsers.add_parser(
        "validate", help="validate given json")

    subparser_validate.add_argument(
        "input_file", type=str, help="path to configuration json"
    )
    
    # Test
    subparser_test = subparsers.add_parser(
        "test", help="send MAC validation packets to the IP"
    )
    subparser_test.add_argument(
        "ip", type=str, help="ip address to test"
    )
    subparser_test.add_argument(
        "input_file", type=str, help="path to configuration json"
    )
    subparser_test.add_argument(
        "-fu","--force_unpair", action="store_true", required=False, help="force unpairs before"
    )


    # Clear
    subparser_clear = subparsers.add_parser("clear", help="erases all config entries on that device via a ConfigSetClear packet")
    subparser_clear.add_argument(
        "ip", type=str, help="ip address to test"
    )
    subparser_clear.add_argument(
         "-fu","--force_unpair", action="store_true", required=False, help="force unpairs before"
    )

    # Configure
    subparser_configure = subparsers.add_parser("configure", help="rolls out the config to that device")

    subparser_configure.add_argument(
        "ip", type=str, help="ip address to test"
    )
    subparser_configure.add_argument(
        "input_file", type=str, help="path to configuration json"
    )
    subparser_configure.add_argument(
         "-fu","--force_unpair", action="store_true", required=False, help="force unpairs before"
    )
    subparser_configure.add_argument(
        "-st","--skip_test", action="store_true", required=False, help="before rolling out the configuration, the MAC configuration test is skipped"
    )
    subparser_configure.add_argument(
        "-sc","--skip_clear", action="store_true", required=False, help="before rolling out the configurations, a general clear of all config slots is skipped"
    )
    subparser_configure.add_argument(
        "-of", "--output_file", required=False, help="redirects the 'json-like' printout from console to the create valid json format in the indicated json file"
    )
    subparser_configure.add_argument(
        "-fw","--force_write", action="store_true", required=False, help="if output file exists already, it will be overwritten"
    )

    args = parser.parse_args()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(execute(args))


if __name__ == "__main__":
    main()
