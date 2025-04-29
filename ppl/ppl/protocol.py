import math
import numbers
import struct
from abc import ABC, abstractmethod
from binascii import hexlify
from collections.abc import Iterable
from enum import Enum, unique
from ipaddress import IPv4Address, ip_address
from typing import Any, Dict, KeysView, List, Tuple, Type, Union

from .exceptions import DeserializeError, DeserializeVersionError, SerializeError
from .macaddress import MacAddress
from .enums import AutoNumber
from .util import ts_print

# logger = StyleAdapter(getLogger(__name__))

# Size (in bytes) that a packet is allowed to have
PACKET_SIZE_LIMIT = 1400


# Parts adapted from https://github.com/facebook/gnlpy


@unique
class subProtocols(AutoNumber):
    INVALID = ()
    DISCOVERY = ()
    PAIRING = ()
    CONFIGURATION = ()
    MEASUREMENT = ()
    DEVICE_CONTROL = ()
    UPDATE = ()


def _unset(x):  # pragma: no cover
    """
    Dummy function used in the code to find out if a default was set.
    Using this function as a default allows to differentiate between a default
    value of None and a default that was not set.
    """
    return x**2


class BaseType(ABC):
    @staticmethod
    @abstractmethod
    def default():
        pass

    @classmethod
    @abstractmethod
    def validate(cls, val: Any):
        pass

    @classmethod
    @abstractmethod
    def pack(cls, val: Any) -> bytes:
        pass

    @classmethod
    @abstractmethod
    def unpack(cls, data: bytes) -> Tuple[int, Any]:
        pass


class _structType(BaseType):
    _fmt = ""
    _size: int
    _packetObj: struct.Struct


def create_struct_fmt_type(fmt: str) -> Type[_structType]:
    class StructFmtType(_structType):
        _fmt = fmt
        _size = struct.calcsize(fmt)
        _packetObj = struct.Struct(fmt)

        @staticmethod
        def default():
            return 0

        @classmethod
        def validate(cls, val: numbers.Number):
            if not isinstance(val, numbers.Number):
                raise SerializeError("Invalid type: {} must be a number!".format(val))
            try:
                cls.pack(val)
            except SerializeError:
                return None
            return val

        @classmethod
        def pack(cls, val: numbers.Number) -> bytes:
            assert val is not None, "Did not validate() before packing."
            try:
                res = cls._packetObj.pack(val)
            except struct.error:
                ts_print("Couldnt pack value")
                ts_print((fmt, val))
                raise SerializeError("Couldnt pack value: {} for format {}".format(val, fmt))
            return res

        @classmethod
        def unpack(cls, data: bytes) -> Tuple[int, Any]:
            try:
                res = cls._packetObj.unpack(data[0 : cls._size])[0]
            except (struct.error, ValueError):
                ts_print("Couldnt unpack value")
                ts_print((fmt, data))
                raise DeserializeError(
                    "Couldnt unpack value: {!s} for format {}".format(hexlify(data), fmt)
                )
            return cls._size, res

    return StructFmtType


def create_tlv_length_packer(fmt: str = ">B", align: int = 4):
    fmt_type = create_struct_fmt_type(fmt)

    class TlvLengthPacker(fmt_type):  # type: ignore
        @staticmethod
        def default():
            raise SerializeError("Must not call default() on length packer.")

        @classmethod
        def pack(cls, val: int) -> bytes:
            assert val is not None, "Did not validate() before packing."
            val = math.ceil((val + fmt_type._size) / align)
            return fmt_type.pack(val)

        @classmethod
        def unpack(cls, data: bytes) -> Tuple[int, Any]:
            lenlen, result = fmt_type.unpack(data)
            if result <= 1:
                raise DeserializeError(
                    "TLV length {} is not allowed. Header + data require length of 2. \nData: {!s}".format(
                        lenlen, data
                    )
                )
            return lenlen, (result * align) - fmt_type._size

    return TlvLengthPacker


def create_enum_type(fmt: str, enumeration: Type[Enum]):
    try:
        enumeration(0)
    except ValueError as e:
        ts_print(e)
        raise SerializeError("Enum {} does not have a zero value.".format(type(enumeration)))

    class StructEnumType(BaseType):
        _size = struct.calcsize(fmt)
        _packetObj = struct.Struct(fmt)

        @staticmethod
        def default():
            return enumeration(0)

        @classmethod
        def validate(cls, val: Any):
            if isinstance(val, int):
                try:
                    val = enumeration(val)
                except ValueError:
                    return None
            if isinstance(val, str):
                try:
                    val = enumeration[val]
                except ValueError:
                    return None
            try:
                cls.pack(val)
            except SerializeError:
                return None
            return val

        @classmethod
        def pack(cls, val: Enum) -> bytes:
            assert val is not None, "Did not validate() before packing."
            if not isinstance(val, enumeration):
                raise SerializeError("Invalid type: {} must be a number!".format(val))
            try:
                res = cls._packetObj.pack(val.value)
            except ValueError:
                ts_print("Couldnt pack value")
                ts_print((fmt, val))
                raise SerializeError("Couldnt pack value: {} for format {}".format(val, fmt))
            return res

        @classmethod
        def unpack(cls, data: bytes) -> Tuple[int, Any]:
            try:
                res = enumeration(cls._packetObj.unpack(data[0 : cls._size])[0])
            except (struct.error, ValueError):
                ts_print("Couldnt unpack value")
                ts_print((fmt, data))
                raise DeserializeError(
                    "Couldnt unpack value: {!s} for format {}".format(hexlify(data), fmt)
                )
            return cls._size, res

    return StructEnumType


class MACAddressType(BaseType):
    __slots__ = ()
    _packetObj = struct.Struct(">Q")

    @staticmethod
    def default():
        return MacAddress(0)

    @classmethod
    def validate(cls, val: Any):
        try:
            return MacAddress(val)
        except ValueError:
            return None

    @classmethod
    def pack(cls, val: MacAddress) -> bytes:
        if not isinstance(val, MacAddress):
            val = cls.validate(val)
            assert val is not None, "Did not validate() before packing."
        try:
            res = cls._packetObj.pack(int(val))[2::]
        except struct.error:
            raise SerializeError("Couldnt pack macaddress: {}".format(val))

        return res

    @classmethod
    def unpack(cls, data: bytes) -> Tuple[int, Any]:
        try:
            res = MacAddress(cls._packetObj.unpack(b"\x00\x00" + data[0:6])[0])
        except struct.error:
            raise DeserializeError("Couldnt unpack macaddress: {!s}".format(hexlify(data)))
        return 6, res


class IPAddressType(BaseType):
    __slots__ = ()
    _packetObj = struct.Struct(">I")

    @staticmethod
    def default():
        return ip_address(0)

    @classmethod
    def validate(cls, val: Any):
        try:
            return ip_address(val)
        except ValueError:
            return None

    @classmethod
    def pack(cls, val: IPv4Address) -> bytes:
        val = cls.validate(val)
        assert val is not None, "Did not validate() before packing."
        try:
            res = cls._packetObj.pack(int(val))
        except struct.error:
            raise SerializeError("Couldnt pack ipaddress: {}".format(val))

        return res

    @classmethod
    def unpack(cls, data: bytes) -> Tuple[int, Any]:
        try:
            res = ip_address(cls._packetObj.unpack(data[0:4])[0])
        except struct.error:
            raise DeserializeError("Couldnt unpack ipaddress: {!s}".format(hexlify(data)))
        return 4, res


class IPAddressLeType(IPAddressType):
    _packetObj = struct.Struct("<I")


class SizeStringType(BaseType):
    __slots__ = ()
    _lengthpacker = create_struct_fmt_type(">H")
    """
    Ensure the string is null terminated when packing and remove the trailing
    \0 when unpacking.
    """

    @staticmethod
    def default():
        return ""

    @classmethod
    def validate(cls, val: str):
        if not isinstance(val, str):
            raise SerializeError("Value must be a string! Have {}".format(val))
        if "\0" in val:
            raise SerializeError("String contains a null character!")
        if len(val) > 0xFFFF:
            raise SerializeError("String length exceeds 65536 characters!")
        return val

    @classmethod
    def pack(cls, val: str) -> bytes:
        assert cls.validate(val) is not None, "Did not validate() before packing."
        byte_data = bytes(val, encoding="latin-1")
        return cls._lengthpacker.pack(len(byte_data)) + byte_data

    @classmethod
    def unpack(cls, data: bytes) -> Tuple[int, Any]:
        string_start, length = cls._lengthpacker.unpack(data)
        try:
            return (length + string_start), bytes(
                data[string_start : string_start + length]
            ).decode()
        except UnicodeDecodeError:
            raise DeserializeError(
                "String data is not a valid string: {!s}".format(
                    hexlify(data[string_start : string_start + length])
                )
            )


def create_array_type(inner_packer, length_packer=create_struct_fmt_type(">H")):
    class ArrayType(BaseType):
        __slots__ = ()
        _lengthpacker = length_packer

        @staticmethod
        def default():
            return []

        @classmethod
        def validate(cls, val: List[Any]):
            if not isinstance(val, Iterable):
                return None
            res = [inner_packer.validate(v) for v in val]
            if any(x is None for x in res):
                return None
            if cls._lengthpacker:
                if cls._lengthpacker.validate(len(val)) is None:
                    return None
            return res

        @classmethod
        def pack(cls, val: List[Any]) -> bytes:
            assert cls.validate(val) is not None, "Did not validate() before packing."
            assert cls._lengthpacker is not None
            res = cls._lengthpacker.pack(len(val))
            _, decoded_len = cls._lengthpacker.unpack(res)
            pad_by = decoded_len - len(val)
            for x in val + [inner_packer.default()] * pad_by:
                res = res + inner_packer.pack(x)
            return res

        @classmethod
        def unpack(cls, data: bytes) -> Tuple[int, Any]:
            res = []
            lenlen, numItems = cls._lengthpacker.unpack(data)
            data = data[lenlen:]
            totalLen = lenlen
            for _ in range(numItems):
                l, val = inner_packer.unpack(data)
                res.append(val)
                data = data[l:]
                totalLen += l
            return totalLen, res

    return ArrayType


def create_fixed_array_type(inner_packer, size: int):
    if _structType in inner_packer.__mro__:
        if inner_packer._fmt[0].isalnum():
            full_fmt = str(size) + inner_packer._fmt
        else:
            full_fmt = inner_packer._fmt[0] + str(size) + inner_packer._fmt[1::]

        fixed_packet = struct.Struct(full_fmt)
        fixed_size = struct.calcsize(full_fmt)

        class FixedOptArrayType(BaseType):
            @staticmethod
            def default():
                return [0] * size

            @classmethod
            def validate(cls, val: List[Any]):
                if not isinstance(val, Iterable):
                    raise SerializeError("Value must be iterable!")
                if len(val) != size:
                    raise SerializeError("Invalid value length: {} vs {}".format(len(val), size))
                try:
                    fixed_packet.pack(*val)
                except struct.error:
                    return None
                return val

            @classmethod
            def pack(cls, val: List[Any]) -> bytes:
                assert cls.validate(val) is not None, "Did not validate() before packing."
                try:
                    return fixed_packet.pack(*val)
                except struct.error:
                    ts_print("Couldnt pack value")
                    ts_print((full_fmt, val))
                    raise SerializeError(
                        "Couldnt pack value: {} for format {}".format(val, full_fmt)
                    )

            @classmethod
            def unpack(cls, data: bytes) -> Tuple[int, Any]:
                try:
                    return fixed_size, list(fixed_packet.unpack(data[0:fixed_size]))
                except (struct.error, ValueError):
                    ts_print("Couldnt unpack value")
                    ts_print((full_fmt, data))
                    raise DeserializeError(
                        "Couldnt unpack value: {!s} for format {}".format(hexlify(data), full_fmt)
                    )

        return FixedOptArrayType

    class FixedArrayType(BaseType):
        __slots__ = ()
        _len = size

        @staticmethod
        def default():
            return [inner_packer.default()] * size

        @classmethod
        def validate(cls, val: List[Any]):
            if not isinstance(val, Iterable):
                raise SerializeError("Value must be iterable!")
            if len(val) != cls._len:
                raise SerializeError("Invalid value length: {} vs {}".format(len(val), cls._len))
            res = [inner_packer.validate(v) for v in val]
            if any(x is None for x in res):
                return None
            return res

        @classmethod
        def pack(cls, val: List[Any]) -> bytes:
            assert cls.validate(val) is not None, "Did not validate() before packing."
            return b"".join(inner_packer.pack(x) for x in val)

        @classmethod
        def unpack(cls, data: bytes) -> Tuple[int, Any]:
            res = []
            totalLen = 0
            for _ in range(cls._len):
                l, val = inner_packer.unpack(data[totalLen:])
                res.append(val)
                totalLen += l
            return totalLen, res

    return FixedArrayType


# Big Endian, Network Byte Order
U8Type = create_struct_fmt_type(">B")
I8Type = create_struct_fmt_type(">b")
U16Type = create_struct_fmt_type(">H")
I16Type = create_struct_fmt_type(">h")
U32Type = create_struct_fmt_type(">I")
I32Type = create_struct_fmt_type(">i")
U64Type = create_struct_fmt_type(">Q")
I64Type = create_struct_fmt_type(">q")
FloatType = create_struct_fmt_type(">f")
DoubleType = create_struct_fmt_type(">d")

# Little Endian
U8LeType = create_struct_fmt_type("<B")
I8LeType = create_struct_fmt_type("<b")
U16LeType = create_struct_fmt_type("<H")
I16LeType = create_struct_fmt_type("<h")
U32LeType = create_struct_fmt_type("<I")
I32LeType = create_struct_fmt_type("<i")
U64LeType = create_struct_fmt_type("<Q")
I64LeType = create_struct_fmt_type("<q")
FloatLeType = create_struct_fmt_type("<f")
DoubleLeType = create_struct_fmt_type("<d")


class BaseMessage(ABC):
    name = ""
    attrs = {}  # type: Dict[int, Any]
    name_to_key = {}  # type: Dict[str, int]
    key_to_name = {}  # type: Dict[int, str]
    key_to_packer = {}  # type: Dict[int, BaseType]

    @abstractmethod
    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def __setitem__(self, key, value):
        pass

    @classmethod
    @abstractmethod
    def validate(cls, val: Any):
        pass

    @abstractmethod
    def set(self, key: Union[str, int], value):
        pass

    @abstractmethod
    def __getitem__(self, key, default=_unset):
        pass

    @abstractmethod
    def get(self, key: Union[str, int], default=_unset):
        pass

    @abstractmethod
    def getDict(self) -> Dict:
        pass

    @classmethod
    @abstractmethod
    def getFields(cls) -> KeysView[str]:
        pass

    @abstractmethod
    def items(self):
        pass

    @abstractmethod
    def __iter__(self):
        pass

    @staticmethod
    @abstractmethod
    def pack(packet_content) -> bytes:
        pass

    @staticmethod
    @abstractmethod
    def unpack(data: bytes):
        pass


def create_packet_type(packet_name: str, *fields: Tuple[str, Any]) -> Type[BaseMessage]:
    class BaseMessageClass(BaseMessage):
        __slots__ = "attrs"
        name_to_key = {}
        key_to_name = {}
        key_to_packer = {}
        for i, (name, packer) in enumerate(fields):
            k = i + 1
            name_to_key[name] = k
            key_to_name[k] = name
            key_to_packer[k] = packer

        name = packet_name

        def __init__(self, **kwargs):
            self.attrs = {}
            for name in sorted(self.name_to_key.keys()):
                if name in kwargs:
                    if kwargs[name] is None:
                        kwargs[name] = self.key_to_packer[self.name_to_key[name]].default()
                    self.set(name, kwargs[name])
                    del kwargs[name]
                else:
                    self.set(name, self.key_to_packer[self.name_to_key[name]].default())
            if kwargs:
                raise SerializeError("Passed superfluous creation parameters: {}".format(kwargs))

        def __contains__(self, key: Union[str, int]):
            if isinstance(key, str):
                return key in self.name_to_key
            return key in self.attrs

        def __eq__(self, other):
            if isinstance(other, self.__class__):
                return self.attrs == other.attrs
            else:
                return False

        # Operator overloading
        def __setitem__(self, key, value):
            self.set(key, value)

        def set(self, key: Union[str, int], value):
            if not isinstance(key, int):
                key = self.name_to_key[key]
            typed_value = self.key_to_packer[key].validate(value)
            if typed_value is None:
                raise SerializeError(
                    "Value is invalid: {} for key {}".format(value, self.key_to_name[key])
                )
            self.attrs[key] = typed_value

        # Operator overloading
        def __getitem__(self, key, default=_unset):
            return self.get(key, default)

        def get(self, key: Union[str, int], default=_unset):
            try:
                if not isinstance(key, int):
                    key = self.name_to_key[key]
                return self.attrs[key]
            except KeyError:
                if default is not _unset:
                    return default
                raise

        def __repr__(self):
            attrs = ["%s=%s" % (self.key_to_name[k], repr(v)) for k, v in self.attrs.items()]
            return "BaseMessage: %s(%s)" % (packet_name, ", ".join(attrs))

        def getDict(self):
            def toDict(v):
                if isinstance(v, BaseMessage):
                    return v.getDict()
                if isinstance(v, list):
                    return [toDict(iv) for iv in v]
                return v

            return {self.key_to_name[k]: toDict(v) for k, v in self.attrs.items()}

        def __iter__(self):
            for k, v in self.attrs.items():
                yield self.key_to_name[k]

        def items(self):
            return [(x, self.get(x)) for x in self]

        @classmethod
        def getFields(cls) -> KeysView[str]:
            return cls.name_to_key.keys()

        @classmethod
        def default(cls):
            res = cls()
            for k in sorted(cls.name_to_key.keys()):
                res[k] = cls.key_to_packer[cls.name_to_key[k]].default()
            return res

        @classmethod
        def validate(cls, val: Any):
            if isinstance(val, BaseMessageClass):
                return val
            if isinstance(val, dict):
                return BaseMessageClass(**val)
            return None

        @staticmethod
        def pack(packet_content: Type[BaseMessage]) -> bytes:
            packed = bytes()
            for k in sorted(packet_content.key_to_packer.keys()):
                if k not in packet_content.attrs:
                    raise SerializeError(
                        "Error: Missing Member {}.".format(packet_content.key_to_name[k])
                    )
                try:
                    x = packet_content.key_to_packer[k].pack(packet_content.attrs[k])
                except (struct.error, KeyError):
                    ts_print(f"Error in {packet_name} Member packing! {packet_content.key_to_name[k] }")
                    raise SerializeError(
                        "Error in {} Member packing! {}".format(
                            packet_name, packet_content.key_to_name[k]
                        )
                    )
                packed += x
            return packed

        @staticmethod
        def unpack(data: bytes) -> Tuple[int, BaseMessage]:
            packet_content = BaseMessageClass()
            totalLen = 0
            for k in sorted(packet_content.key_to_packer.keys()):
                try:
                    l, v = packet_content.key_to_packer[k].unpack(data)
                except (struct.error, DeserializeError):
                    ts_print(f"Error in {packet_name} Member unpacking! {packet_content.key_to_name[k]}")
                    raise DeserializeError(
                        "Error in {} Member unpacking! {}".format(
                            packet_name, packet_content.key_to_name[k]
                        )
                    )
                packet_content.set(k, v)
                data = data[l:]
                totalLen += l
            return totalLen, packet_content

    return BaseMessageClass


def create_tlv_packet_type(packet_name: str) -> Type[BaseMessage]:
    ParentType = create_packet_type(
        packet_name,
        ("component", U8Type),
        ("valueId", U16Type),
        ("data", create_array_type(U8Type, length_packer=create_tlv_length_packer())),
    )
    comp_pack = ParentType.key_to_packer[ParentType.name_to_key["component"]]
    val_pack = ParentType.key_to_packer[ParentType.name_to_key["valueId"]]
    data_pack = ParentType.key_to_packer[ParentType.name_to_key["data"]]

    class TlvMessageClass(ParentType):
        @staticmethod
        def pack(packet_content: BaseMessage) -> bytes:
            component = packet_content["component"]
            valueId = packet_content["valueId"]
            data = packet_content["data"]

            full_data = list(comp_pack.pack(component) + val_pack.pack(valueId)) + data
            if data_pack.validate(full_data) is None:
                raise SerializeError("Error in {} validation!".format(packet_name))
            return data_pack.pack(full_data)

        @staticmethod
        def unpack(data: bytes) -> Tuple[int, Type[BaseMessage]]:
            cLen, component = comp_pack.unpack(data[1:])
            vLen, valueId = val_pack.unpack(data[1 + cLen :])
            length, array = data_pack.unpack(data)

            packet_content = TlvMessageClass(
                component=component,
                valueId=valueId,
                data=array[cLen + vLen :],
            )
            return length, packet_content

    return TlvMessageClass


class SubProtocol(ABC):
    subprot: Enum = None
    version: int = 0
    cmd: int = 0
    packet_content = BaseMessage

    @abstractmethod
    def __init__(self, packet_content: BaseMessage):
        pass

    @abstractmethod
    def get_packet(self) -> BaseMessage:
        pass

    @abstractmethod
    def get_subprotocol(self) -> subProtocols:
        pass

    @staticmethod
    @abstractmethod
    def pack(msg) -> bytes:
        pass

    @staticmethod
    @abstractmethod
    def unpack(data: bytes):
        pass


def create_subprotocol(
    subprotocol: subProtocols, prot_version: int, *packets, **kwargs
) -> Type[SubProtocol]:
    name_to_key = {}
    key_to_name = {}
    key_to_packet_content_type = {}
    for i, packet_content_type in enumerate(packets):
        name = packet_content_type.name
        key = i + 1
        name_to_key[name] = key
        key_to_name[key] = name
        key_to_packet_content_type[key] = packet_content_type

    @protocol_class
    class SubProtocolClass(SubProtocol):
        subprot = subprotocol
        version = prot_version

        def __init__(self, packet_content: Type[BaseMessage]):
            if packet_content.name not in name_to_key:
                raise SerializeError(
                    "Packettype not part of protocol: {}".format(packet_content.name)
                )
            self.packet_content = packet_content
            self.cmd = name_to_key[self.packet_content.name]

        def get_packet(self):
            return self.packet_content

        def get_subprotocol(self) -> subProtocols:
            return self.subprot

        def __repr__(self):
            return "Protocol: %s (cmd=%s, packet_content=%s), version=%d" % (
                subprotocol,
                repr(key_to_name[self.cmd]),
                repr(self.packet_content),
                self.version,
            )

        @staticmethod
        def pack(msg: Type[SubProtocol]) -> bytes:
            return struct.pack(str(">B"), msg.cmd) + key_to_packet_content_type[msg.cmd].pack(
                msg.packet_content
            )

        @staticmethod
        def unpack(data: bytes) -> SubProtocol:
            if len(data) < 1:
                raise DeserializeError("Packet without content cannot be deseralized!")
            (cmd,) = struct.unpack(str(">B"), data[:1])
            if cmd not in key_to_packet_content_type:
                raise DeserializeError(
                    "Invalid packettype for protocol: {} | {}".format(cmd, subprotocol)
                )
            length, packet_content = key_to_packet_content_type[cmd].unpack(data[1:])
            if length != len(data[1:]):
                raise DeserializeError(
                    "Packet has superfluous(unread) bytes: {!s}".format(data[length:])
                )
            return SubProtocolClass(packet_content)

        @staticmethod
        def getRegisteredPackets():
            return key_to_packet_content_type

    return SubProtocolClass


# This is a global map of unpackers.  The @protocol_class decorator inserts
# new message classes into this map so it can be used for the purpose of
# deserializing packets messages
__cmd_unpack_map = {}  # type: Dict[Enum, Type[SubProtocol]]

HDR_STR = ">HBBH"
HDR_SIZE = struct.calcsize(HDR_STR)


def get_protocol_versions() -> Dict[Enum, int]:
    return {v.subprot: v.version for v in __cmd_unpack_map.values()}


def protocol_class(msg_prot: Type[SubProtocol]):
    assert (
        msg_prot.subprot.value not in __cmd_unpack_map
    ), "Message class {}:{} is already defined.".format(msg_prot.subprot, msg_prot.subprot.value)

    __cmd_unpack_map[msg_prot.subprot.value] = msg_prot

    return msg_prot

def serialize_message(msg_prot: SubProtocol, sequence_number: int) -> bytes:
    subprot = msg_prot.subprot
    msg_bytes = msg_prot.pack(msg_prot)

    if len(msg_bytes) > PACKET_SIZE_LIMIT:
        raise SerializeError(
            "Packets of length {} are not supported! Max is {}.".format(
                len(msg_bytes), PACKET_SIZE_LIMIT
            )
        )
    try:
        hdr_bytes = (
            struct.pack(
                HDR_STR, len(msg_bytes) + HDR_SIZE, sequence_number, subprot.value, msg_prot.version
            )
            + msg_bytes
        )
        return hdr_bytes
    except struct.error:
        raise SerializeError(
            "Could not serialize header packet {}".format(
                (len(msg_bytes) + HDR_SIZE, sequence_number, subprot.value)
            )
        )


def deserialize_message(data) -> Tuple[int, SubProtocol]:
    if len(data) < HDR_SIZE:
        raise DeserializeError("Too small packet: {}".format(len(data)))
    (length, sequence_number, subprot, prot_ver) = struct.unpack(HDR_STR, data[:HDR_SIZE])
    if subprot not in __cmd_unpack_map:
        raise DeserializeError("Unregistered subprotocol: %d" % subprot)
    if prot_ver != __cmd_unpack_map[subprot].version:
        raise DeserializeVersionError(
            "Subprotcol {} version doesn't match: have {} want {}".format(
                subprot, prot_ver, __cmd_unpack_map[subprot].version
            ),
            subprot,
            prot_ver,
            sequence_number,
        )
    if length != len(data):
        raise DeserializeError("Packet has superfluous bytes: {}".format(data[length:]))
    msg = __cmd_unpack_map[subprot].unpack(data[HDR_SIZE:length])
    return sequence_number, msg
