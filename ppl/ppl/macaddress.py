import string
from typing import Union


class MacAddressValueError(ValueError):
    pass


class MacAddress:
    __slots__ = ("_mac", "__weakref__")

    @classmethod
    def _parse_from_string(cls, mac_str):
        if not mac_str:
            raise MacAddressValueError("MAC cannot be empty.")

        octets = mac_str.split(":")
        if len(octets) != 6:
            raise MacAddressValueError("Expected 6 octets in %r" % mac_str)

        try:
            return int.from_bytes(map(cls._parse_octet, octets), "big")
        except ValueError as exc:
            raise MacAddressValueError("%s in %r" % (exc, mac_str)) from None

    @classmethod
    def _parse_octet(cls, octet_str):
        if not octet_str:
            raise ValueError("Empty octet not permitted")
        # Whitelist the characters, since int() allows a lot of bizarre stuff.
        if not all(c in string.hexdigits for c in octet_str):
            raise ValueError("Only hexdigits permitted in %r" % octet_str)
        # We do the length check second, since the invalid character error
        # is likely to be more informative for the user
        if len(octet_str) > 2:
            raise ValueError("At most 2 characters permitted in %r" % octet_str)
        # Convert to integer (we know digits are legal)
        octet_int = int(octet_str, 16)
        return octet_int

    def __init__(self, value: Union[bytes, str, int]):
        if isinstance(value, bytes):
            if len(value) != 6:
                raise MacAddressValueError(
                    "%r has invalid number of octets for MAC address" % value
                )
            self._mac = int.from_bytes(value, "big")
        elif isinstance(value, int):
            if value > 0xFFFFFFFFFFFF:
                raise MacAddressValueError("%r is more than 6 bytes long" % value)
            self._mac = value
        else:
            # Assume input argument to be string or any object representation
            # which converts into a formatted MAC string.
            self._mac = self._parse_from_string(str(value))

    def __int__(self):
        return self._mac

    def __eq__(self, other):
        try:
            return self._mac == other._mac
        except AttributeError:
            return NotImplemented

    def __lt__(self, other):
        return int(self) < int(other)

    def __le__(self, other):
        return int(self) <= int(other)

    def __gt__(self, other):
        return int(self) > int(other)

    def __ge__(self, other):
        return int(self) >= int(other)

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, str(self))

    def __str__(self):
        return ":".join(map("{:02x}".format, self._mac.to_bytes(6, "big")))

    def __reduce__(self):
        return self.__class__, (self._mac,)

    def __hash__(self):
        return hash(hex(int(self._mac)))
