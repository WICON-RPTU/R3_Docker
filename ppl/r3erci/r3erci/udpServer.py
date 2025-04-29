import asyncio
import inspect
import socket
import traceback
from contextlib import contextmanager
from ipaddress import IPv4Address
from typing import Any, Callable, Coroutine, Iterator, List, Optional, Tuple

from r3erci.constants import PORT, ErciCmd, ErciPosHeader, GetPacketLength
from r3erci.util import ts_print

CRType = Coroutine[Any, Any, bool]
InternalSubscriberType = Callable[[ErciCmd, int, bytes, Tuple[str, int]], CRType]
ExternalSubscriberType = Callable[[ErciCmd, int, bytes, Tuple[str, int]], CRType]


class UdpServerProtocol(asyncio.BaseProtocol):
    def __init__(self, handler):
        self.handler = handler
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, sender):
        try:
            asyncio.ensure_future(self.handler(data, sender))
        except Exception as e:
            ts_print(e)


class UdpServer:
    subscribers = []  # type: List[InternalSubscriberType]
    sock = None  # type: socket.socket

    def __init__(self, ownaddress: str = "0.0.0.0", ownport: int = PORT):
        try:
            IPv4Address(ownaddress)
        except ValueError:
            raise ValueError(f"{ownaddress} is no valid IPv4 address")
        try:
            ownport = int(ownport)
        except ValueError:
            raise ValueError(f"{ownport} is not an integer")
        self.dispatchLock = asyncio.Lock()
        self.openSocket(ownaddress, ownport)

    def openSocket(self, ownaddress: str, ownport: int, timeout: float = 0.5) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception:
            pass
        self.sock.settimeout(timeout)
        self.sock.bind((ownaddress, ownport))

        loop = asyncio.get_event_loop()
        listen = loop.create_datagram_endpoint(
            lambda: UdpServerProtocol(self.receiveHandler),
            sock=self.sock,
        )
        if loop.is_running():
            loop.create_task(listen)
        else:
            transport, protocol = loop.run_until_complete(listen)

    def sendPacket(self, data: bytes, address: IPv4Address, port: int) -> None:
        self.sock.sendto(data, (str(address), port))

    async def receiveHandler(self, data: bytes, address: Tuple[str, int]) -> None:
        le, plt = GetPacketLength(None)
        if len(data) < le:
            ts_print(
                f"Response from {address[0]}: \033[0;31mShort frame!\033[0m ({len(data)}B vs. expect {str(plt).lower} {le}B)"
            )
            return

        try:
            cmd = ErciCmd(data[ErciPosHeader.COMMAND])
        except ValueError:
            cmd = None
        seq = data[ErciPosHeader.SEQUENCE]

        await self.dispatchPacket(cmd, seq, data, address)

    async def dispatchPacket(
        self, command: ErciCmd, sequence: int, message: bytes, address: Tuple[str, int]
    ) -> None:
        async with self.dispatchLock:
            processed = False
            for proc in self.subscribers:
                try:
                    if await proc(command, sequence, message, address):
                        processed = True
                except Exception as e:
                    proc_name = getattr(proc, "__qualname__", str(type(proc)))
                    pack_name = getattr(message, "name", type(message))
                    ts_print(
                        f"An error occured during processing of Packet-Type {pack_name} in subscriber {proc_name}"
                    )
                    ts_print(e)
                    ts_print(traceback.format_exc())
            if not processed:
                ts_print(
                    f"Received an unprocessed packet. Command {str(command)}, seq {sequence} from {address[0]}:{address[1]}"
                )

    def _check_subscriber(self, subscriber) -> None:
        if not callable(subscriber):
            raise AttributeError("Subscriber is not callable")
        if not inspect.iscoroutinefunction(subscriber):
            raise AttributeError("Only couroutines can subscribe to packets.")
        # Check for the parameters required
        required = ["command", "sequence", "message", "address"]
        if set(required) > set(subscriber.__code__.co_varnames):
            ts_print(subscriber)
            ts_print(subscriber.__code__.co_varnames)
            raise AttributeError("Subscriber does not posess required parameters.")

    def subscribe(self, subscriber: InternalSubscriberType) -> None:
        self._check_subscriber(subscriber)
        self.subscribers.append(subscriber)

    def unsubscribe(self, subscriber: InternalSubscriberType) -> None:
        if subscriber not in self.subscribers:
            raise ValueError("Not a valid subscriber!")
        self.subscribers.remove(subscriber)

    @contextmanager
    def subscriberFilterContext(
        self,
        subscriber: ExternalSubscriberType,
        filterCmd: Optional[ErciCmd] = None,
        filterSeq: Optional[int] = None,
        filterAddr: Optional[str] = None,
    ) -> Iterator[None]:
        async def filtered_message(
            command: ErciCmd, sequence: int, message: bytes, address: Tuple[str, int]
        ) -> bool:
            if filterCmd is not None and filterCmd != command:
                return False
            if filterSeq is not None and filterSeq != sequence:
                return False
            if filterAddr is not None and filterAddr != address[0]:
                return False
            return await subscriber(command, sequence, message, address)

        # logger.debug("Subscribing filter SP {} seq {} addr {}", filterCmd, filterSeq, filterAddr)
        self._check_subscriber(subscriber)
        self.subscribe(filtered_message)
        try:
            yield
        finally:
            # logger.debug("Unsubscribing filter SP {} seq {} addr {}", filterCmd, filterSeq, filterAddr)
            self.unsubscribe(filtered_message)
