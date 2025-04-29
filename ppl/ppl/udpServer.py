import asyncio
import inspect
import socket
import traceback
import copy
import ppl.packetDefinitions as pd
from contextlib import contextmanager
from ipaddress import IPv4Address
from typing import Any, Callable, Coroutine, Iterator, List, Optional, Tuple

from .constants import CLIENTPORT, SERVERPORT
from ppl.util import ts_print
from . import protocol
from .protocol import subProtocols
from ppl.enums import getReliabilityEnum, getOptimizationEnum, getSecurityModeEnum, getFilterActionEnum

CRType = Coroutine[Any, Any, bool]
ProtSubscriberType = Callable[[int, protocol.BaseMessage, Tuple[str, int]], CRType]
SubscriberType = Callable[[subProtocols, int, protocol.BaseMessage, Tuple[str, int]], CRType]

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
    subscribers = []  # type: List[SubscriberType]
    sock = None  # type: socket.socket
    
    packet_sequence = 0

    def __init__(self, ownaddress: str = "0.0.0.0", ownport: int = SERVERPORT):
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
    
    def getNextSeq(self) -> int:
        self.packet_sequence = (self.packet_sequence + 1) % 0x100
        return self.packet_sequence

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

    def createPacket(self, protocolMessage: protocol.SubProtocol,
        seq: Optional[int] = None,) -> Tuple[int | None, bytes | None]:
        if seq is None:
            seq = self.getNextSeq()
        seq, rawData = pd.serialize_message(protocolMessage, seq=seq)
        if not rawData:
            ts_print("Could not serialize invalid packet: {}", protocolMessage)
            return None
        return rawData

    def sendPacket(self, data: bytes, address: IPv4Address, port = CLIENTPORT) -> None:
        """use createPacket() to generate the data input for this method"""
        self.sock.sendto(data, (str(address), port))
        pass

    async def receiveHandler(self, data: bytes, address: Tuple[str, int]) -> None:
        # Check length, identifier and strip padding
        subProtocol, sequence, message = pd.deserialize_message(data)
        if message is None or sequence is None:
            ts_print(f"Packet from {address} could not be deserialized. Prot {subProtocol} Seq {sequence}")
        else:
            await self.dispatchPacket(subProtocol, sequence, message, address)

    async def dispatchPacket(
        self, subProtocol: subProtocols, sequence: int, message: bytes, address: Tuple[str, int]
    ) -> None:
        async with self.dispatchLock:
            processed = False
            for proc in self.subscribers:
                try:
                    if await proc(subProtocol, sequence, message, address):
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
                # ts_print(f"Received an unprocessed packet. Type {message.name}, sequence {sequence} from {address[0]}:{address[1]}")
                # ts_print("Content was: {}".format(message))
                return

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

    def subscribe(self, subscriber: SubscriberType) -> None:
        self._check_subscriber(subscriber)
        self.subscribers.append(subscriber)

    def unsubscribe(self, subscriber: SubscriberType) -> None:
        if subscriber not in self.subscribers:
            raise ValueError("Not a valid subscriber!")
        self.subscribers.remove(subscriber)

    @contextmanager
    def subscriberFilterContext(
        self,
        subscriber: ProtSubscriberType,
        *args,
        filterSP: Optional[Any] = None,
        filterSeq: Optional[int] = None,
        filterAddr: Optional[str] = None
    ) -> Iterator[None]:
        async def filtered_message(sprot, sequence: int, message, address: Tuple[str, int]) -> bool:
            if filterSP is not None and filterSP != sprot:
                return False
            if filterSeq is not None and filterSeq != sequence:
                return False
            if filterAddr is not None and filterAddr != address[0]:
                return False
            return await subscriber(sequence, message, address)

        # ts_print("Subscribing filter SP {} seq {} addr {}", filterSP, filterSeq, filterAddr)
        self.subscribe(filtered_message)
        try:
            yield
        finally:
            # ts_print("Unsubscribing filter SP {} seq {} addr {}", filterSP, filterSeq, filterAddr)
            self.unsubscribe(filtered_message)
            
    
    def createPacketDataMacConfig(self, json_data, isOutput = False):
        # Initialize packet fields with default values
        packet_data = {
        'latency': 1,
        'TTRT': 0,
        'payloadSize': 10,
        'reliability': 'NONE',
        'stationCount': 2,
        'optimization': "EXACT",
        'dataRate': 0,
        'addr_net_id': 1,
        'addr_mac_addr_len': 1,
        'addr_mac': '',
        'externalRelay': False,
        'echoing': False,
        'logging': False,
        'hopping': False,
        'ctrlPacketRate': 0,
        'payloadPacketRate': 0,
        'ctrlPacketReps': 0,
        'payloadPacketReps': 0,
        'stationPTTs': 0,
        'totalPTTs': 2,
        'isStatic': True,
        'isAnchor': False,
        'allowHandover': False,
        'allowBcRep': False,
        'subnets': [],
        'securityMode': 'DISABLED',
        'queue_sizes': []
        }

        data = []
        for network_config in json_data.values():
            mac_config = network_config.get('macConfiguration', {})
            station_config = network_config.get('stationConfiguration', {})
            llc_config = network_config.get('llcConfiguration', {}).get('priorityFilters', [])
            subnet_config = network_config.get('subnetConfiguration', [])
            if not isOutput:
                currPacket: dict = copy.deepcopy(packet_data)   
                currPacket['latency'] = mac_config.get('latency', packet_data['latency'])
                currPacket['TTRT'] = mac_config.get('ttrt', packet_data['TTRT'])
                currPacket['payloadSize'] = mac_config.get('payloadSize', packet_data['payloadSize'])
                currPacket['reliability'] = getReliabilityEnum(mac_config.get('reliability', packet_data['reliability']))
                currPacket['stationCount'] = mac_config.get('stationCount', packet_data['stationCount'])
                currPacket['optimization'] = getOptimizationEnum(mac_config.get('configOptimization', packet_data['optimization']))
                currPacket['dataRate'] = mac_config.get('dataRate', packet_data['dataRate'])
                currPacket['addr_net_id'] = mac_config.get('networkAddress', packet_data['addr_net_id'])
                # addr_mac_addr_len
                currPacket['addr_mac'] = station_config.get('macAddress', packet_data['addr_mac'])
                currPacket['externalRelay'] = station_config.get('options', {}).get('isExtRelay', packet_data['externalRelay'])
                currPacket['echoing'] = mac_config.get('options', {}).get('allowRelaying', packet_data['echoing'])
                currPacket['logging'] = mac_config.get('options', {}).get('allowLogging', packet_data['logging'])
                currPacket['hopping'] = mac_config.get('options', {}).get('allowFreqHop', packet_data['hopping'])
                # ctrPacketRate
                # payloadPacketRate
                # ctrlPacketReps
                # payloadPacketReps
                currPacket['stationPTTs'] = station_config.get('stationPTT', packet_data['stationPTTs'])
                currPacket['totalPTTs'] = mac_config.get('totalPTT', packet_data['totalPTTs'])
                currPacket['isStatic'] = station_config.get('options', {}).get('isStatic', packet_data['isStatic'])
                currPacket['isAnchor'] = station_config.get('options', {}).get('isAnchor', packet_data['isAnchor'])
                currPacket['allowHandover'] = mac_config.get('options', {}).get('allowHandover', packet_data['allowHandover'])
                currPacket['allowBcRep'] = mac_config.get('options', {}).get('allowBcRep', packet_data['allowBcRep'])
                highestPriority = 0
                for filter in llc_config:
                    actionValue = getFilterActionEnum(filter['action']).value
                    if actionValue > highestPriority:
                        highestPriority = actionValue
                currPacket['queue_sizes'] = station_config.get('queueSizes', [0 for _ in range(highestPriority + 2)])
                currPacket['securityMode'] = getSecurityModeEnum(mac_config.get('securityMode', packet_data['securityMode']))   
                # Process subnets
                for subnet in subnet_config:
                    currPacket['subnets'].append(pd.SubnetEntry(**{
                        'addr_subnet_id': subnet.get('subnetAddress', 0),
                        'channel': subnet.get('channel', 0),
                        'txPower': subnet.get('txPower', 0.0)
                    }))
            else:
                currPacket = {}
                currPacket['latency'] = mac_config.get('latency', None)
                currPacket['ttrt'] = mac_config.get('ttrt', None)
                currPacket['payloadSize'] = mac_config.get('payloadSize', None)
                currPacket['reliability'] = mac_config.get('reliability', None)
                currPacket['stationCount'] = mac_config.get('stationCount', None)
                currPacket['configOptimization'] = mac_config.get('configOptimization', None)
                currPacket['dataRate'] = mac_config.get('dataRate', packet_data['dataRate'])
                currPacket['networkAddress'] = mac_config.get('networkAddress', None)
                # addr_mac_addr_len
                currPacket['macAddress'] = station_config.get('macAddress', None)
                currPacket['isExtRelay'] = station_config.get('options', {}).get('isExtRelay', None)
                currPacket['allowRelaying'] = mac_config.get('options', {}).get('allowRelaying', None)
                currPacket['allowLogging'] = mac_config.get('options', {}).get('allowLogging', None)
                currPacket['allowFreqHop'] = mac_config.get('options', {}).get('allowFreqHop', None)
                # ctrPacketRate
                # payloadPacketRate
                # ctrlPacketReps
                # payloadPacketReps
                currPacket['stationPTT'] = station_config.get('stationPTT', None)
                currPacket['totalPTT'] = mac_config.get('totalPTT', None)
                currPacket['isStatic'] = station_config.get('options', {}).get('isStatic', None)
                currPacket['isAnchor'] = station_config.get('options', {}).get('isAnchor', None)
                currPacket['allowHandover'] = mac_config.get('options', {}).get('allowHandover', None)
                currPacket['allowBcRep'] = mac_config.get('options', {}).get('allowBcRep', None)
                currPacket['queueSizes'] = station_config.get('queueSizes', None)
                currPacket['securityMode'] = mac_config.get('securityMode', None)
                # Process subnets
                currPacket['subnets'] = []
                for subnet in subnet_config:
                    currPacket['subnets'].append(({
                        'subnetAddress': subnet.get('subnetAddress', 0),
                        'channel': subnet.get('channel', 0),
                        'txPower': subnet.get('txPower', 0.0)
                    }))
                for field in copy.deepcopy(currPacket):
                    if currPacket[f'{field}'] is None:
                        currPacket.pop(f'{field}')
            data.append(currPacket)
        return data
    
    def createPacketDataSetGlobalHostConfig(self, deviceConfig, isOutput = False):
        packet = {}
        if not isOutput:
            packet['dhcp_client'] = True if deviceConfig['useDhcp'] else False
            packet['static_ip'] = deviceConfig.get('ip', '0.0.0.0')
            packet['subnet_mask'] = deviceConfig.get('netmask', '0.0.0.0')
            packet['gateway'] = deviceConfig.get('gateway', '0.0.0.0')
            packet['nameserver'] = deviceConfig.get('nameserver', '0.0.0.0')
            packet['timeserver'] = deviceConfig.get('timeserver', '0.0.0.0')
        else:
            packet = {**deviceConfig}
            if 'comment' in deviceConfig:
                packet.pop('comment')
        return packet
    
    def createPacketDataSetHostConfig(self, json_data, isOutput = False):
        data = []

        set_host_config_data = {
            'multicast_group': '225.224.223.0',
            'multicast_port': 32145,
            'traffic_filters': [],
            'routes': []
        }
        for config in json_data.values():
            llc_config = config.get('llcConfiguration', {})
            if isOutput:
                data.append(llc_config)
                continue
            curr_data = copy.deepcopy(set_host_config_data)
            curr_data['multicast_group'] = llc_config.get('mcgroup', set_host_config_data['multicast_group'])
            curr_data['multicast_port'] = llc_config.get('mcport', set_host_config_data['multicast_port'])
            if 'priorityFilters' in llc_config:
                for filter in llc_config['priorityFilters']:
                    modEntries = []
                    for rule in filter['rules']:
                        pos, val = rule
                        modEntries.append({'index': rule[pos], 'value': rule[val]})
                    modFilter = {'action': getFilterActionEnum(filter['action']), 'entries': modEntries}             
                    curr_data['traffic_filters'].append(pd.TrafficFilter(**modFilter))
            if 'routes' in llc_config:
                for route in llc_config['routes']:
                    macAddress, extAddress = route
                    modRoute = {'macaddress': route[macAddress], 'llcaddress': route[extAddress]}
                    curr_data['routes'].append(pd.RTLookup(**modRoute))
            data.append(curr_data)
        return data