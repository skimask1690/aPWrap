import time
import sys
import ctypes
from ctypes import c_void_p, c_uint, c_int, create_string_buffer
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SYSTEM = sys.platform

IS_64BIT = sys.maxsize > 2**32
ARCH = "64" if IS_64BIT else "32"

if SYSTEM == "win32":
    LIB_PATH = BASE_DIR / "lib" / f"aplib{ARCH}.dll"
    LIBRARY = ctypes.WinDLL(str(LIB_PATH))
    CALLBACK_TYPE = ctypes.WINFUNCTYPE
elif SYSTEM == "linux":
    LIB_PATH = BASE_DIR / "lib" / f"aplib{ARCH}.so"
    LIBRARY = ctypes.CDLL(str(LIB_PATH))
    CALLBACK_TYPE = ctypes.CFUNCTYPE
else:
    raise RuntimeError("Unsupported platform")


APLIB_CALLBACK = CALLBACK_TYPE(c_int, c_uint, c_uint, c_uint, c_void_p)
APLIB_ERROR = 0xFFFFFFFF


# -------------------- Compression API --------------------
LIBRARY.aP_workmem_size.argtypes = [c_uint]
LIBRARY.aP_workmem_size.restype = c_uint

LIBRARY.aP_max_packed_size.argtypes = [c_uint]
LIBRARY.aP_max_packed_size.restype = c_uint

LIBRARY.aP_pack.argtypes = [
    c_void_p,
    c_void_p,
    c_uint,
    c_void_p,
    APLIB_CALLBACK,
    c_void_p,
]
LIBRARY.aP_pack.restype = c_uint


# -------------------- Decompression API --------------------
LIBRARY.aP_depack_asm.argtypes = [c_void_p, c_void_p]
LIBRARY.aP_depack_asm.restype = c_uint


# -------------------- Callback --------------------
@APLIB_CALLBACK
def progress(inpos, outpos, stage, cbparam):
    return 1


# -------------------- Compression --------------------
def compress_data(data: bytes, use_verbose=False) -> bytes:
    size = len(data)

    workmem = LIBRARY.aP_workmem_size(size)
    max_out = LIBRARY.aP_max_packed_size(size)

    if use_verbose:
        print("[aPLib] Starting compression...")
        print(f"[aPLib] Input = {size} bytes")
        print(f"[aPLib] Workmem = {workmem} bytes")
        print(f"[aPLib] Max output = {max_out} bytes")

    src = create_string_buffer(data, size)
    dst = create_string_buffer(max_out)
    wm = create_string_buffer(workmem)

    packed = LIBRARY.aP_pack(src, dst, size, wm, progress, None)

    if packed == APLIB_ERROR:
        raise RuntimeError("aP_pack failed")

    if use_verbose:
        print(f"[aPLib] Compressed = {packed} bytes")

    # prepend original size header
    header = size.to_bytes(4, "little")

    return header + dst.raw[:packed]


def compress_file(inp, out, use_verbose=False):
    inp = Path(inp)
    out = Path(out)

    data = inp.read_bytes()

    compressed = compress_data(data, use_verbose)

    out.write_bytes(compressed)

    original_size = len(data)
    packed_size = len(compressed) - 4  # exclude size header

    ratio = (packed_size / original_size) * 100 if original_size else 0

    print(f"\nInput file      : {inp}")
    print(f"Output file     : {out}")
    print(f"Input size      : {original_size} bytes")
    print(f"Compressed size : {packed_size} bytes")
    print(f"Compression     : {ratio:.2f}%")


# -------------------- Decompression --------------------
def decompress_data(data: bytes, use_verbose=False) -> bytes:
    if len(data) < 4:
        raise RuntimeError("Invalid compressed data (missing header)")

    out_size = int.from_bytes(data[:4], "little")
    compressed = data[4:]

    if use_verbose:
        print("[aPLib] Starting decompression...")
        print(f"[aPLib] Compressed input = {len(compressed)} bytes")
        print(f"[aPLib] Expected output = {out_size} bytes")

    src = create_string_buffer(compressed, len(compressed))
    dst = create_string_buffer(out_size)

    start = time.time()

    result = LIBRARY.aP_depack_asm(src, dst)

    elapsed = time.time() - start

    if result == 0:
        raise RuntimeError("aP_depack_asm failed")

    if use_verbose:
        print("[aPLib] Decompression completed")
        print(f"[aPLib] Time taken = {elapsed:.6f}s")

    return dst.raw[:out_size]


def decompress_file(inp, out, use_verbose=False):
    inp = Path(inp)
    out = Path(out)

    data = inp.read_bytes()

    decompressed = decompress_data(data, use_verbose)

    out.write_bytes(decompressed)

    out_size = len(decompressed)
    compressed_size = len(data) - 4

    print(f"\nInput file       : {inp}")
    print(f"Output file      : {out}")
    print(f"Compressed size  : {compressed_size} bytes")
    print(f"Decompressed size: {out_size} bytes")


# -------------------- CLI --------------------
if __name__ == "__main__":
    script_name = Path(sys.argv[0]).name

    if len(sys.argv) < 4:
        print(f"Usage: {script_name} <pack|depack> <input> <output> [-verbose]")
        sys.exit(1)

    mode = sys.argv[1]

    use_verbose = "-verbose" in sys.argv

    if mode == "pack":
        compress_file(sys.argv[2], sys.argv[3], use_verbose)

    elif mode == "depack":
        decompress_file(sys.argv[2], sys.argv[3], use_verbose)

    else:
        print("Unknown mode. Use 'pack' or 'depack'.")
        sys.exit(1)
