import asyncio
from datetime import datetime

from r3erci.client import ErciClient
from r3erci.constants import ErciCmd, ErciState
from r3erci.exceptions import ErciException, ResponseError, TimeoutError
from r3erci.util import ts_print, color_string_fail, colors


class ErciSequencer:
    def __init__(self, address):
        self.address = address
        self.client = ErciClient()

    async def run(self):
        # wait for device to be online
        ts_print("-> Waiting for the device")
        is_online = False
        msg = None
        while not is_online:
            try:
                msg = await self.client.send_command(self.address, ErciCmd.STATE_QUERY)
            except TimeoutError:
                pass
            except ResponseError as e:
                ts_print(f"Error: {str(e)}")
                ts_print("Exit now...")
                return

            if msg is not None:
                is_online = True
                break

        ts_print("-> device is online")

        # check state, abort if in FAULT state
        if msg["type"] != str(ErciCmd.STATE_RESPONSE):
            ts_print(
                f"-> {color_string_fail('device did not return a STATE_RESPONSE !')} (have {msg['type']})"
            )
            ts_print("Exit now...")
            return
        if msg["state"] == str(ErciState.FAULT):
            ts_print("-> device is in the FAULT state !")
            ts_print("Exit now...")
            return

        # wait for device to leave the STARTUP state if necessary
        is_ready = False
        while not is_ready:
            if msg is not None and msg["type"] == str(ErciCmd.STATE_RESPONSE):
                if msg["state"] == str(ErciState.READY) or msg["state"] == str(
                    ErciState.RUNNING
                ):
                    is_ready = True
                    break

            try:
                msg = await self.client.send_command(self.address, ErciCmd.STATE_QUERY)
            except TimeoutError:
                pass
            except ResponseError as e:
                ts_print(f"Error: {str(e)}")
                ts_print("Exit now...")
                return

            await asyncio.sleep(1)

        ts_print("-> device is operable")

        # stop device if it is running
        if msg["state"] == str(ErciState.RUNNING):
            ts_print("-> device is running, stopping...")
            try:
                msg = await self.client.send_command(self.address, ErciCmd.STOP)
            except TimeoutError:
                ts_print(
                    f'-> {color_string_fail("failed to stop the device:")} No response'
                )
                ts_print("Exit now...")
                return
            except ResponseError as e:
                ts_print(f"Error: {str(e)}")
                ts_print("Exit now...")
                return

            if msg["success"] is False:
                ts_print(
                    f'-> {color_string_fail("failed to stop the device:")} {msg["status_msg"]}'
                )
                return

            try:
                msg = await self.client.send_command(self.address, ErciCmd.STATE_QUERY)
            except ErciException as e:
                ts_print(f"Error: {str(e)}")
                ts_print("Exit now...")
                return

        start_time = datetime.now()
        num_cycles = 0

        while True:

            if num_cycles % 2 == 0:
                config_id = 1
                ring_id = 11
                antenna_id = 1
            else:
                config_id = 2
                ring_id = 22
                antenna_id = 2

            ts_print()
            ts_print(f"Selecting ConfigID {config_id}")
            try:
                msg = await self.client.send_command(
                    self.address,
                    ErciCmd.SELECT_CONFIG,
                    config_id=config_id,
                    ring_id=ring_id,
                    antenna_id=antenna_id,
                )
            except TimeoutError:
                ts_print(
                    f'-> {color_string_fail("failed to select the config:")} No response'
                )
                break
            except ResponseError as e:
                ts_print(f"Error: {str(e)}")
                await asyncio.sleep(1)
                break
            if msg["success"] is False:
                ts_print(
                    f'-> {color_string_fail("failed to select the config:")} {msg["status_msg"]}'
                )
                break

            try:
                msg = await self.client.send_command(self.address, ErciCmd.STATE_QUERY)
            except ErciException as e:
                ts_print(f"Error: {str(e)}")

            ts_print("Starting the ring")
            try:
                msg = await self.client.send_command(self.address, ErciCmd.START)
            except ErciException as e:
                ts_print(f"Error: {str(e)}")
                break
            if msg["success"] is False:
                ts_print(
                    f'-> {color_string_fail("failed to start the device:")} {msg["status_msg"]}'
                )
                break

            try:
                msg = await self.client.send_command(self.address, ErciCmd.STATE_QUERY)
            except ErciException as e:
                ts_print(f"Error: {str(e)}")

            await asyncio.sleep(5.0)

            ts_print("Stopping")
            try:
                msg = await self.client.send_command(self.address, ErciCmd.STOP)
            except ErciException as e:
                ts_print(f"Error: {str(e)}")
                break
            if msg["success"] is False:
                ts_print(
                    f'-> {color_string_fail("failed to stop the device:")} {msg["status_msg"]}'
                )
                break

            try:
                msg = await self.client.send_command(self.address, ErciCmd.STATE_QUERY)
            except ErciException as e:
                ts_print(f"Error: {str(e)}")

            num_cycles = num_cycles + 1

        print("")
        ts_print("Shutting down")

        try:
            msg = await self.client.send_command(self.address, ErciCmd.STATE_QUERY)
        except ErciException as e:
            ts_print(f"Error: {str(e)}")

        # check state, abort if in FAULT state
        if msg["type"] == str(ErciCmd.STATE_RESPONSE):
            if msg["state"] == str(ErciState.RUNNING):
                ts_print("device is in the RUNNING state, sending STOP...")
                try:
                    msg = await self.client.send_command(self.address, ErciCmd.STOP)
                    if msg["success"] is False:
                        ts_print(
                            f'-> {color_string_fail("failed to stop the device:")} {msg["status_msg"]}'
                        )
                except ErciException as e:
                    ts_print(f"Error: {str(e)}")

        time_elapsed = (datetime.now() - start_time).total_seconds()

        print("")
        print(
            "The test loop was running for {:.2f}s (= {:.2f}min = {:.2f}h)".format(
                time_elapsed, time_elapsed / 60, time_elapsed / 3600
            )
        )
        print(f"Ran {num_cycles} cycles")


async def async_main(address: str) -> None:
    sequencer = ErciSequencer(address)
    await sequencer.run()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Testing sequencer simulating the PLC part of ERCI. Use with erci_ereb.py."
    )
    parser.add_argument("address", help="The IP/FQDN of the EREB")

    args = parser.parse_args()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(async_main(args.address))
    except (KeyboardInterrupt, SystemExit):
        print()
        pass


if __name__ == "__main__":
    main()
