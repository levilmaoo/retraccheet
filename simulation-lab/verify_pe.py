"""Fail unless the supplied executable is a PE with AMD64 machine type."""
from pathlib import Path
import struct
import sys

data = Path(sys.argv[1]).read_bytes()
if data[:2] != b"MZ":
    raise SystemExit("Missing DOS header")
offset = struct.unpack_from("<I", data, 0x3c)[0]
if data[offset:offset+4] != b"PE\0\0":
    raise SystemExit("Missing PE signature")
machine = struct.unpack_from("<H", data, offset+4)[0]
if machine != 0x8664:
    raise SystemExit("Expected AMD64; got 0x%04x" % machine)
print("Verified Windows AMD64 PE")
