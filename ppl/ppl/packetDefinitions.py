from enum import Enum
from typing import Dict, List, Optional, Tuple

from . import protocol
from .enums import (
    ConfigStorageMode,
    FilterAction,
    MeasType,
    SecurityMode,
    ifaceType,
    nodeState,
    nukeAction,
)
from .protocol import (
    BaseMessage,
    DeserializeError,
    DeserializeVersionError,
    FloatType,
    I32LeType,
    IPAddressLeType,
    IPAddressType,
    MACAddressType,
    SerializeError,
    SizeStringType,
    SubProtocol,
    U8Type,
    U16Type,
    U32LeType,
    U32Type,
    U64Type,
    create_array_type,
    create_enum_type,
    create_fixed_array_type,
    create_packet_type,
    create_subprotocol,
    create_tlv_packet_type,
    subProtocols,
)

from ppl.util import ts_print


MEAS_MAXSTATIONS = 10

"""
Packet type / layout explanation

    Each packet starts with a header:

    struct {
        uint16_t messageLength;
        uint8_t sequenceNumber;
        uint8_t subProtocol;
        uint16_t protocolVersion;
        uint8_t packetType;
    }

    where:
     - messageLength: Total length of the encoded message (including length field, so total payload Bytes)
     - sequenceNumber: Used only where explicitly indicated to map queries to their responses
     - subProtocol: See define above, specified which suprotcol is used
     - protocolVersion: Indicates the used version of subProtocol supported. Any mismatch of version => Packets will not decode
     - packetType: Depends on the subProtocol. A value of 1 will always be of type GenericError, followed by the packets specified using
                   create_subprotocol

    All members in both header and payload will be encoded in NetworkByte Order.
    No padding to align with special hardware boundaries will be inserted.

    Each packet specified using create_packet_type can make use of the following specifiers:
     - Base type specifiers:
            U8Type
            I8Type
            U16Type
            I16Type
            U32Type
            I32Type
            U64Type
            I64Type
            FloatType
            DoubleType
        Encoded using a direct byte copy of the corresponding trivial type. So e.g. U8Type will be a length of 1, containing the u8 directly.

     - create_enum_type(encType, enum)
            Convenience wrapper around one of the above base types. Most used will be '>B' for encType, which corresponds to U8Type.
            Same byte encoding as underlying type, just wraps en/decoding to an enum Type
     - IPAddressType
            Same byte encoding as U32Type, but en/decodes to IPv4Address type
     - SizeStringType
            Encodes a variable length string. Encoding will start with 2 Byte U16Type to encode the string length, followed by string data as chars
            of the specified length
     - create_fixed_array_type(<encoder>, length)
            Encodes a fixed sized array of type encoder. So e.g. create_fixed_array_type(U32Type, 10) will encode the equivalent of
                `uint32_t values[10];`
            without any additional bytes.
     - create_array_type(<encoder>)
            Encodes a variable sized array. Starts with a U16Type encoded length of the array,
            followed by a number of repetitions of the given encoder
     - create_packet_type
            Encodes effectively a struct. Does not yet include a packetType. Can be used in any place where an <encoder> is needed.
            Members are specified using a list of
                (<name>, <encoder>)
            Which are laid out in the order they are specified.
     - create_subprotocol
            Takes a number of packet_types and ties them together into a subprotocol.
            First value is the subProtocol written to any packet header,
            Next value is the protocolVersion written to each packet header.
            Following this are the specified packets, which are assigned to the packetType key in the packet header starting with index One.

            So given the following spec:

                TestSubProt = create_subprotocol(
                    subProtocols.TEST, 4,
                    GenericError,
                    GetNodeState)


            Specifies a protocol of version 4 with an subProtocol identifier of subProtocols.TEST where
                packetType == 1 => GenericError
                packetType == 2 => GetNodeState
"""


GenericError = create_packet_type(
    "GenericError",
    ("ErrorMsg", SizeStringType),
)

DeprecatedPacket = create_packet_type(
    "DeprecatedPacket",
)

# ========================================
# ======== Discovery subprotocol =========
# ========================================
GetNodeState = create_packet_type(
    "GetNodeState",
)

KeyValuePair = create_packet_type(
    "Version",
    ("name", SizeStringType),
    ("value", SizeStringType),
)

SubProtocolInfo = create_packet_type(
    "SubProtocolInfo", ("protocol", create_enum_type(">B", subProtocols)), ("version", U8Type)
)

IFaceInfo = create_packet_type(
    "IFaceInfo",
    ("type", create_enum_type(">B", ifaceType)),
    ("name", SizeStringType),
    ("MAC", MACAddressType),
    ("ip", IPAddressType),
)

NodeState = create_packet_type(
    "NodeState",
    ("state", create_enum_type(">B", nodeState)),
    ("serverIP", IPAddressType),
    ("hasStaticConfig", U8Type),
    ("ifaces", create_array_type(IFaceInfo)),
    ("versions", create_array_type(KeyValuePair)),
    ("features", create_array_type(SubProtocolInfo)),
)

GetPyrtmfState = create_packet_type(
    "GetPyrtmfState",
)

PyrtmfState = create_packet_type(
    "PyrtmfState",
    ("state", U8Type),
    ("version", SizeStringType),
)


DiscovSubProt = create_subprotocol(
    subProtocols.DISCOVERY,
    2,
    GenericError,
    GetNodeState,
    NodeState,
    GetPyrtmfState,
    PyrtmfState,
)

# ========================================
# ========  Pairing subprotocol  =========
# ========================================
PairNode = create_packet_type("PairNode")

PairSuccess = create_packet_type("PairSuccess")

UnpairNode = create_packet_type("UnpairNode")

PairSubProt = create_subprotocol(
    subProtocols.PAIRING, 1, GenericError, PairNode, PairSuccess, UnpairNode
)


# ========================================
# ====== Configuration subprotocol =======
# ========================================

SetGlobalHostConfig = create_packet_type(
    "SetGlobalHostConfig",
    ("dhcp_client", U8Type),
    ("static_ip", IPAddressType),
    ("subnet_mask", IPAddressType),
    ("gateway", IPAddressType),
    ("nameserver", IPAddressType),
    ("timeserver", IPAddressType),
)

RTLookup = create_packet_type(
    "RTLookup",
    ("macaddress", MACAddressType),
    ("llcaddress", MACAddressType),
)

FilterEntry = create_packet_type(
    "FilterEntry",
    ("index", U8Type),
    ("value", U8Type),
)

TrafficFilter = create_packet_type(
    "TrafficFilter",
    ("action", create_enum_type(">B", FilterAction)),
    ("entries", create_array_type(FilterEntry)),
)

SetHostConfig = create_packet_type(
    "SetHostConfig",
    ("multicast_group", IPAddressType),
    ("multicast_port", U16Type),
    ("traffic_filters", create_array_type(TrafficFilter)),
    ("routes", create_array_type(RTLookup)),
)

AddHostRoutes = create_packet_type(
    "AddHostRoutes",
    ("routes", create_array_type(RTLookup)),
)

SubnetEntry = create_packet_type(
    "SubnetEntry",
    ("addr_subnet_id", U8Type),
    ("channel", U8Type),
    ("txPower", FloatType),
)

_cfgFields = [
    ("latency", U32Type),
    ("TTRT", U32Type),
    ("payloadSize", U16Type),
    ("reliability", U8Type),
    ("stationCount", U8Type),
    ("optimization", U8Type),
    ("dataRate", U16Type),
    ("addr_net_id", U8Type),
    ("addr_mac_addr_len", U8Type),
    ("addr_mac", MACAddressType),
    ("externalRelay", U8Type),
    ("echoing", U8Type),
    ("logging", U8Type),
    ("hopping", U8Type),
    ("ctrlPacketRate", U8Type),
    ("payloadPacketRate", U8Type),
    ("ctrlPacketReps", U8Type),
    ("payloadPacketReps", U8Type),
    ("stationPTTs", U8Type),
    ("totalPTTs", U8Type),
    ("isStatic", U8Type),
    ("isAnchor", U8Type),
    ("allowHandover", U8Type),
    ("allowBcRep", U8Type),
    ("subnets", create_array_type(SubnetEntry)),
    ("securityMode", create_enum_type(">B", SecurityMode)),
    ("queue_sizes", create_array_type(U8Type)),
]

ValidateMACConfig = create_packet_type(
    "ValidateMACConfig",
    *_cfgFields,
)

SetMACConfig = create_packet_type(
    "SetMACConfig",
    *_cfgFields,
)

ZeusSecurityConfig = create_packet_type(
    "ZeusSecurityConfig",
    ("addr_mac", MACAddressType),
    ("zeusblob", create_array_type(U8Type)),
)

StartConfigSetTransaction = create_packet_type(
    "StartConfigSetTransaction",
    ("storage", create_enum_type(">B", ConfigStorageMode)),
    ("slots", create_array_type(U8Type)),
)

SelectConfigSlot = create_packet_type(
    "SelectConfigSlot",
    ("slotid", U8Type),
)

FinalizeConfigSlot = create_packet_type(
    "FinalizeConfigSlot",
)

ApplyConfigSet = create_packet_type(
    "ApplyConfigSet",
    ("UID", U64Type),
    ("slotid", U8Type),
)

CommitConfigSet = create_packet_type(
    "CommitConfigSet",
    ("UID", U64Type),
)

ReadConfigSetUID = create_packet_type(
    "ReadConfigSetUID",
    ("UID", U64Type),
)

ClearConfigSet = create_packet_type(
    "ClearConfigSet",
)

ConfigSubProt = create_subprotocol(
    subProtocols.CONFIGURATION,
    8,
    GenericError,
    ValidateMACConfig,
    SetMACConfig,
    SetHostConfig,
    AddHostRoutes,
    SetGlobalHostConfig,
    ZeusSecurityConfig,
    StartConfigSetTransaction,
    SelectConfigSlot,
    FinalizeConfigSlot,
    ApplyConfigSet,
    CommitConfigSet,
    ReadConfigSetUID,
    ClearConfigSet,
)

# ========================================
# ======= Measurement subprotocol ========
# ========================================
MeasurementStart = create_packet_type("MeasurementStart")

DemoStatus = create_packet_type(
    "DemoStatus",
    ("__packetNumber", U32LeType),
    ("totalTransmissions", U32LeType),
    ("dataPackets", create_fixed_array_type(U32LeType, 5)),
    ("rcvdToken", create_fixed_array_type(U32LeType, 5)),
    ("rcvdPackets", create_fixed_array_type(U32LeType, 5)),
    ("delayProfile", create_fixed_array_type(U32LeType, 29)),
    ("recoveryTypes", create_fixed_array_type(U32LeType, 3)),
    ("stateTransitions", create_fixed_array_type(U32LeType, 5)),
    ("sentData", create_fixed_array_type(U32LeType, 2)),
    ("dataPacketProb", create_fixed_array_type(U32LeType, 2)),
    ("destination", IPAddressLeType),
    ("relays", create_fixed_array_type(U32LeType, MEAS_MAXSTATIONS)),
    ("selfRing", U32LeType),
    ("successor", U32LeType),
    ("channel", U32LeType),
    ("snrs", create_fixed_array_type(I32LeType, MEAS_MAXSTATIONS)),
    ("rxAbort", U32LeType),
    ("scrambledPackets", create_fixed_array_type(U32LeType, 3)),
    ("idleExpiry", create_fixed_array_type(U32LeType, MEAS_MAXSTATIONS - 1)),
)

SingleLink = create_packet_type(
    "SingleLink",
    ("destination", IPAddressType),
    ("payloadSize", U16Type),
    ("multiplier", U8Type),
    ("priority", U8Type),
    ("streamID", U8Type),
)

_measCfgFields = [
    ("measType", create_enum_type(">B", MeasType)),
    ("periodicity", U32Type),
    ("deadline", U32Type),
    ("packetNumber", U32Type),
    ("measIp", IPAddressType),
    ("links", create_array_type(SingleLink)),
]

MeasValidateConfig = create_packet_type(
    "MeasValidateConfig",
    *_measCfgFields,
)

MeasSetConfig = create_packet_type(
    "MeasSetConfig",
    *_measCfgFields,
)

SingleLinksStatus = create_packet_type(
    "SingleLinksStatus",
    ("streamID", U8Type),
    ("packetNumber", U32Type),
    ("failedPackets", U32Type),
    ("delayProfile", create_fixed_array_type(U32Type, 29)),
    ("rcvdOK", U32Type),
    ("rcvdFailed", U32Type),
    ("lastSeqNum", U32Type),
    ("outOfOrder", U32Type),
    ("duplicates", U32Type),
    ("txJitter", create_fixed_array_type(U32Type, 33)),
    ("rxJitter", create_fixed_array_type(U32Type, 33)),
)

MeasLinkStatus = create_packet_type(
    "MeasLinkStatus",
    ("links", create_array_type(SingleLinksStatus)),
)

MeasurementStop = create_packet_type(
    "MeasurementStop",
    ("links", create_array_type(SingleLinksStatus)),
)

RequestLog = create_packet_type(
    "RequestLog",
    ("_placeholder", create_fixed_array_type(U8Type, 16)),
)

ProtLogData = create_packet_type(
    "ProtLogData",
    ("index", U16Type),
    ("total", U16Type),
    ("debugLength", U16Type),
    ("padding", U16Type),
    ("data", create_fixed_array_type(U8Type, 1008)),
)

ProtLogHeader = create_packet_type(
    "ProtLogHeader",
    ("entrySize", U8Type),
    ("data", create_fixed_array_type(U8Type, 1380)),
)

MeasSubProt = create_subprotocol(
    subProtocols.MEASUREMENT,
    5,
    GenericError,
    MeasurementStart,
    MeasurementStop,
    DemoStatus,
    MeasValidateConfig,
    MeasSetConfig,
    MeasLinkStatus,
    RequestLog,
    ProtLogData,
    ProtLogHeader,
)


# ========================================
# ====== DeviceControl subprotocol =======
# ========================================
DeviceNuke = create_packet_type(
    "DeviceNuke",
    ("mode", create_enum_type(">B", nukeAction)),
)

DeviceDevelopment = create_packet_type(
    "DeviceDevelopment",
    ("component", U8Type),
    ("module", U8Type),
    ("command", U8Type),
    ("level", U8Type),
    ("wasExecuted", U8Type),
    ("isDisabled", U8Type),
    ("isSupported", U8Type),
    ("wasFiltered", U8Type),
    ("isDeprecated", U8Type),
    ("data", create_array_type(U32Type)),
)

DiagnosticTLV = create_tlv_packet_type(
    "DiagnosticTLV",
)

DeviceDiagnostics = create_packet_type(
    "DeviceDiagnostics",
    ("diagnostics", create_array_type(DiagnosticTLV)),
)

DeviceBridgeStart = create_packet_type(
    "DeviceBridgeStart",
)

DeviceBridgeStop = create_packet_type(
    "DeviceBridgeStop",
)

DevControlSubProt = create_subprotocol(
    subProtocols.DEVICE_CONTROL,
    4,
    GenericError,
    DeprecatedPacket,
    DeviceNuke,
    DeviceDevelopment,
    DeviceDiagnostics,
    DeprecatedPacket,
    DeviceBridgeStart,
    DeviceBridgeStop,
)

# ========================================
# ======    Update subprotocol     =======
# ========================================
UpdateInfo = create_packet_type(
    "UpdateInfo",
    ("versions", create_array_type(KeyValuePair)),
    ("meta", create_array_type(KeyValuePair)),
)

UpdateResponse = create_packet_type(
    "UpdateResponse",
    ("updates", create_array_type(UpdateInfo)),
)

UpdateQuery = create_packet_type(
    "UpdateQuery",
)

UpdateStart = create_packet_type(
    "UpdateStart",
)

UpdateDownloadProgress = create_packet_type(
    "UpdateDownloadProgress",
    ("progress", U16Type),
    ("total", U16Type),
)

UpdateDownloadFinish = create_packet_type(
    "UpdateDownloadFinish",
)

UpdateSuccess = create_packet_type(
    "UpdateSuccess",
)

UpdaterSubProt = create_subprotocol(
    subProtocols.UPDATE,
    3,
    GenericError,
    UpdateQuery,
    UpdateResponse,
    UpdateStart,
    UpdateDownloadProgress,
    UpdateDownloadFinish,
    UpdateSuccess,
)


def get_features() -> Dict[Enum, int]:
    return {k: v for k, v in protocol.get_protocol_versions().items()}


def supports_feature(feature_set: List[SubProtocolInfo], feature: subProtocols) -> bool:
    """
    Checks wether the given feature is supported by a given feature set

    :param      feature_set:  Set of features to check against (as a list of subProtocols type)
    :param      feature:      Feature to check for

    :returns:   True if the feature is supported (+ can be used by us)
    :rtype:     bool
    """
    vers = protocol.get_protocol_versions()
    for f in feature_set:
        if f["protocol"] == feature:
            if feature in vers and f["version"] == vers[feature]:
                return True

    return False


def deserialize_message_raw(data: bytes) -> Tuple[Optional[int], Optional[SubProtocol]]:
    return protocol.deserialize_message(data)


def deserialize_message(data: bytes) -> Tuple[subProtocols, Optional[int], Optional[BaseMessage]]:
    try:
        seq, msg = protocol.deserialize_message(data)
        return msg.get_subprotocol(), seq, msg.get_packet()
    except DeserializeVersionError as e:
        if e.subprot == subProtocols.DISCOVERY.value:
            ts_print(f"Version mismatch during deserialization: {e}")
        else:
            
            ts_print(f"Version mismatch during deserialization: {e}")
        return e.subprot, e.sequence_number, None
    except DeserializeError as e:
        ts_print(f"Could not deserialize: {e}")
        return subProtocols.INVALID, None, None


def serialize_message(msg: protocol.SubProtocol, seq: int) -> Tuple[Optional[int], Optional[bytes]]:
    try:
        return seq, protocol.serialize_message(msg, seq)
    except SerializeError as e:
        ts_print(f"Could not serialize: {e}")
        return None, None
