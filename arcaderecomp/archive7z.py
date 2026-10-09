"""Read 7z ROM archive members using the system's libarchive library.

The archive is streamed in order, including unwanted files, because solid 7z
archives may require earlier entries to be decompressed before later entries.
No proprietary ROM data is included in the repository.
"""
import ctypes
import ctypes.util
from pathlib import Path


class SevenZipReadError(ValueError):
    pass


def read_7z_members(filename, allowed_names, max_file_size=128 * 1024 * 1024):
    """Return {basename: (archive_member_name, bytes)} for selected ROM names."""
    libname = ctypes.util.find_library("archive")
    if not libname:
        raise SevenZipReadError(
            "Reading 7z requires system libarchive; alternatively convert 7z to ZIP"
        )
    dll = ctypes.CDLL(libname)
    pointer = ctypes.c_void_p

    def bind(symbol, arguments, output):
        function = getattr(dll, symbol)
        function.argtypes = arguments
        function.restype = output
        return function

    make = bind("archive_read_new", [], pointer)
    formats = bind("archive_read_support_format_all", [pointer], ctypes.c_int)
    filters = bind("archive_read_support_filter_all", [pointer], ctypes.c_int)
    open_file = bind("archive_read_open_filename",
                     [pointer, ctypes.c_char_p, ctypes.c_size_t], ctypes.c_int)
    next_header = bind("archive_read_next_header",
                       [pointer, ctypes.POINTER(pointer)], ctypes.c_int)
    member_name = bind("archive_entry_pathname", [pointer], ctypes.c_char_p)
    member_size = bind("archive_entry_size", [pointer], ctypes.c_int64)
    read = bind("archive_read_data", [pointer, pointer, ctypes.c_size_t], ctypes.c_ssize_t)
    reason = bind("archive_error_string", [pointer], ctypes.c_char_p)
    free = bind("archive_read_free", [pointer], ctypes.c_int)

    reader = make()
    if not reader:
        raise SevenZipReadError("Unable to allocate archive reader")
    found = {}
    try:
        formats(reader)
        filters(reader)
        path = str(Path(filename).absolute()).encode("utf-8")
        if open_file(reader, path, 10240) != 0:
            raise SevenZipReadError(f"Unable to open 7z archive: {reason(reader)!r}")
        header = pointer()
        buffer = ctypes.create_string_buffer(256 * 1024)
        while True:
            state = next_header(reader, ctypes.byref(header))
            if state == 1:  # ARCHIVE_EOF
                break
            if state != 0:
                raise SevenZipReadError(f"Unable to parse 7z entry: {reason(reader)!r}")
            name = (member_name(header) or b"").decode("utf-8", "replace")
            basename = name.replace("\\", "/").rsplit("/", 1)[-1]
            selected = basename in allowed_names and not name.endswith("/")
            if selected and basename in found:
                raise SevenZipReadError(f"Duplicate 7z ROM entry: {basename}")
            if selected and member_size(header) > max_file_size:
                raise SevenZipReadError(f"7z ROM member too large: {basename}")
            payload = bytearray() if selected else None
            total = 0
            while True:
                length = read(reader, buffer, len(buffer))
                if length < 0:
                    raise SevenZipReadError(f"Corrupt 7z entry {name!r}: {reason(reader)!r}")
                if length == 0:
                    break
                total += length
                if selected:
                    if total > max_file_size:
                        raise SevenZipReadError(f"7z ROM entry exceeds limit: {basename}")
                    payload.extend(buffer.raw[:length])
            if selected:
                found[basename] = (name, bytes(payload))
    finally:
        free(reader)
    return found
