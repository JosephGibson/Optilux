"""Windows named pipes through ctypes, for the mod client and the protocol fake
(docs/mod-protocol.md#transport).

Every handle is opened overlapped: on a synchronous handle Windows serializes all I/O, so a
reader thread blocked in ReadFile would block every write until a line arrived. Each read and
write here has its own OVERLAPPED and event and waits for its own completion, so one reader
thread and any number of writers share a handle. The server side (the fake's) uses the mod's
flags and a DACL with one ACE for this user. Windows-only: ctypes.WinDLL is resolved on first
use, so the module imports anywhere (the release workflow runs on Linux).
"""

import ctypes
import threading
import time
from types import SimpleNamespace

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
PIPE_ACCESS_DUPLEX = 0x3
# winbase.h; jna-platform lacks it, the mod declares the same value (docs/plans/m1.md P12).
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
PIPE_REJECT_REMOTE_CLIENTS = 0x8
# PIPE_TYPE_BYTE, PIPE_READMODE_BYTE and PIPE_WAIT are 0.
PIPE_MODE = PIPE_REJECT_REMOTE_CLIENTS
OPEN_MODE = PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE | FILE_FLAG_OVERLAPPED
BUFFER_BYTES = 64 * 1024
SE_KERNEL_OBJECT = 6
DACL_SECURITY_INFORMATION = 0x4
SDDL_REVISION_1 = 1
TOKEN_QUERY = 0x8
TOKEN_USER_CLASS = 1
ERROR_FILE_NOT_FOUND = 2
ERROR_ACCESS_DENIED = 5
ERROR_BROKEN_PIPE = 109
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_PIPE_BUSY = 231
ERROR_NO_DATA = 232
ERROR_PIPE_NOT_CONNECTED = 233
ERROR_PIPE_CONNECTED = 535
ERROR_OPERATION_ABORTED = 995
ERROR_IO_PENDING = 997
# The errors that mean the other end is gone or this end was closed: an end of stream.
ENDED = (ERROR_BROKEN_PIPE, ERROR_NO_DATA, ERROR_PIPE_NOT_CONNECTED, ERROR_OPERATION_ABORTED)
# open_client retries an absent or busy pipe at this interval.
RETRY_SECONDS = 0.05
# close() waits this long for the operations it cancelled to finish before closing the handle.
CLOSE_WAIT_SECONDS = 5.0


class PipeError(OSError):
    """A pipe call that failed; the message names the call and the Windows error."""


_API: SimpleNamespace | None = None


def api() -> SimpleNamespace:
    """kernel32 and advapi32 with their signatures, loaded once."""
    global _API
    if _API is not None:
        return _API
    from ctypes import wintypes

    class OVERLAPPED(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    class SECURITY_ATTRIBUTES(ctypes.Structure):  # noqa: N801 (the Windows name)
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    handle, dword, boolean = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL
    pov = ctypes.POINTER(OVERLAPPED)
    pdword = ctypes.POINTER(dword)
    pulong = ctypes.POINTER(wintypes.ULONG)
    for func, args, result in (
        (
            k32.CreateFileW,
            [wintypes.LPCWSTR, dword, dword, ctypes.c_void_p, dword, dword, handle],
            handle,
        ),
        (
            k32.CreateNamedPipeW,
            [wintypes.LPCWSTR, dword, dword, dword, dword, dword, dword, ctypes.c_void_p],
            handle,
        ),
        (k32.ConnectNamedPipe, [handle, pov], boolean),
        (k32.DisconnectNamedPipe, [handle], boolean),
        (k32.ReadFile, [handle, ctypes.c_void_p, dword, pdword, pov], boolean),
        (k32.WriteFile, [handle, ctypes.c_void_p, dword, pdword, pov], boolean),
        (k32.GetOverlappedResult, [handle, pov, pdword, boolean], boolean),
        (k32.CancelIoEx, [handle, pov], boolean),
        (k32.CreateEventW, [ctypes.c_void_p, boolean, boolean, wintypes.LPCWSTR], handle),
        (k32.CloseHandle, [handle], boolean),
        (k32.GetNamedPipeServerProcessId, [handle, pulong], boolean),
        (k32.GetNamedPipeClientProcessId, [handle, pulong], boolean),
        (k32.GetCurrentProcess, [], handle),
        (k32.LocalFree, [ctypes.c_void_p], ctypes.c_void_p),
        (adv.OpenProcessToken, [handle, dword, ctypes.POINTER(handle)], boolean),
        (adv.GetTokenInformation, [handle, ctypes.c_int, ctypes.c_void_p, dword, pdword], boolean),
        (adv.ConvertSidToStringSidW, [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)], boolean),
        (
            adv.ConvertStringSecurityDescriptorToSecurityDescriptorW,
            [wintypes.LPCWSTR, dword, ctypes.POINTER(ctypes.c_void_p), pulong],
            boolean,
        ),
        (
            adv.GetSecurityInfo,
            [handle, ctypes.c_int, dword, ctypes.c_void_p, ctypes.c_void_p]
            + [ctypes.POINTER(ctypes.c_void_p)] * 3,
            dword,
        ),
        (
            adv.ConvertSecurityDescriptorToStringSecurityDescriptorW,
            [ctypes.c_void_p, dword, dword, ctypes.POINTER(wintypes.LPWSTR), pulong],
            boolean,
        ),
    ):
        func.argtypes = args
        func.restype = result
    _API = SimpleNamespace(
        k32=k32,
        adv=adv,
        OVERLAPPED=OVERLAPPED,
        SECURITY_ATTRIBUTES=SECURITY_ATTRIBUTES,
        invalid=wintypes.HANDLE(-1).value,
        wintypes=wintypes,
    )
    return _API


def fail(call: str, error: int | None = None) -> PipeError:
    code = ctypes.get_last_error() if error is None else error
    return PipeError(f"{call} failed: Windows error {code}")


class Pipe:
    """One end of a byte-mode pipe on an overlapped handle: a reader thread and writers share it.
    read() returns b"" when the other end is gone or this end was closed."""

    def __init__(self, handle: int) -> None:
        self.handle = handle
        self._lock = threading.Condition()
        self._active = 0
        self._closed = False

    def _begin(self) -> bool:
        with self._lock:
            if self._closed:
                return False
            self._active += 1
            return True

    def _end(self) -> None:
        with self._lock:
            self._active -= 1
            self._lock.notify_all()

    def _io(self, call, buffer, size: int) -> int | None:
        """One overlapped ReadFile or WriteFile waited to completion: the bytes moved, or None
        when the pipe ended."""
        w = api()
        overlapped = w.OVERLAPPED()
        overlapped.hEvent = w.k32.CreateEventW(None, True, False, None)
        if not overlapped.hEvent:
            raise fail("CreateEventW")
        try:
            if not call(self.handle, buffer, size, None, ctypes.byref(overlapped)):
                error = ctypes.get_last_error()
                if error in ENDED:
                    return None
                if error != ERROR_IO_PENDING:
                    raise fail(call.__name__, error)
            moved = w.wintypes.DWORD()
            if not w.k32.GetOverlappedResult(
                self.handle, ctypes.byref(overlapped), ctypes.byref(moved), True
            ):
                error = ctypes.get_last_error()
                if error in ENDED:
                    return None
                raise fail("GetOverlappedResult", error)
            return moved.value
        finally:
            w.k32.CloseHandle(overlapped.hEvent)

    def read(self, size: int) -> bytes:
        if not self._begin():
            return b""
        try:
            buffer = ctypes.create_string_buffer(size)
            moved = self._io(api().k32.ReadFile, buffer, size)
            return b"" if moved is None else buffer.raw[:moved]
        finally:
            self._end()

    def write(self, data: bytes) -> None:
        if not self._begin():
            raise PipeError("the pipe is closed")
        try:
            sent = 0
            while sent < len(data):
                chunk = ctypes.create_string_buffer(data[sent:], len(data) - sent)
                moved = self._io(api().k32.WriteFile, chunk, len(data) - sent)
                if not moved:
                    raise PipeError("the other end of the pipe is gone")
                sent += moved
        finally:
            self._end()

    def close(self) -> None:
        """Cancel this handle's pending I/O, wait for it to end, then let the handle go. The
        cancel is repeated: an operation past its start check may issue its call after one."""
        w = api()
        with self._lock:
            if self._closed:
                return
            self._closed = True
            deadline = time.monotonic() + CLOSE_WAIT_SECONDS
            while self._active and time.monotonic() < deadline:
                w.k32.CancelIoEx(self.handle, None)
                self._lock.wait(RETRY_SECONDS)
        self._release()

    def _release(self) -> None:
        api().k32.CloseHandle(self.handle)


def open_client(name: str, timeout: float) -> Pipe:
    """The client end of `name`, retried while the pipe is absent or serving another client."""
    w = api()
    deadline = time.monotonic() + timeout
    while True:
        handle = w.k32.CreateFileW(
            name, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None
        )
        if handle != w.invalid:
            return Pipe(handle)
        error = ctypes.get_last_error()
        if error not in (ERROR_FILE_NOT_FOUND, ERROR_PIPE_BUSY):
            raise fail(f"CreateFileW {name}", error)
        if time.monotonic() >= deadline:
            what = "does not exist" if error == ERROR_FILE_NOT_FOUND else "serves another client"
            raise PipeError(f"the pipe {name} {what} after {timeout:g} s")
        time.sleep(RETRY_SECONDS)


def server_pid(pipe: Pipe) -> int:
    """The pid of the process serving the pipe (GetNamedPipeServerProcessId)."""
    w = api()
    pid = w.wintypes.ULONG()
    if not w.k32.GetNamedPipeServerProcessId(pipe.handle, ctypes.byref(pid)):
        raise fail("GetNamedPipeServerProcessId")
    return pid.value


def client_pid(pipe: Pipe) -> int:
    w = api()
    pid = w.wintypes.ULONG()
    if not w.k32.GetNamedPipeClientProcessId(pipe.handle, ctypes.byref(pid)):
        raise fail("GetNamedPipeClientProcessId")
    return pid.value


def current_user_sid() -> str:
    """This process token's user SID as a string (S-1-5-21-...)."""
    w = api()
    token = w.wintypes.HANDLE()
    if not w.adv.OpenProcessToken(w.k32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise fail("OpenProcessToken")
    try:
        needed = w.wintypes.DWORD()
        w.adv.GetTokenInformation(token, TOKEN_USER_CLASS, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        if not w.adv.GetTokenInformation(
            token, TOKEN_USER_CLASS, buffer, needed.value, ctypes.byref(needed)
        ):
            raise fail("GetTokenInformation")
        sid = ctypes.c_void_p.from_buffer(buffer).value  # TOKEN_USER.User.Sid comes first
        text = w.wintypes.LPWSTR()
        if not w.adv.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise fail("ConvertSidToStringSidW")
        try:
            return text.value
        finally:
            w.k32.LocalFree(text)
    finally:
        w.k32.CloseHandle(token)


def dacl_sddl(pipe: Pipe) -> str:
    """The pipe's DACL in SDDL, read through this end's handle (READ_CONTROL comes with
    GENERIC_READ): D:(A;;FA;;;<sid>) is one ACE granting this user full access."""
    w = api()
    descriptor = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    error = w.adv.GetSecurityInfo(
        pipe.handle,
        SE_KERNEL_OBJECT,
        DACL_SECURITY_INFORMATION,
        None,
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if error:
        raise fail("GetSecurityInfo", error)
    try:
        text = w.wintypes.LPWSTR()
        if not w.adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, SDDL_REVISION_1, DACL_SECURITY_INFORMATION, ctypes.byref(text), None
        ):
            raise fail("ConvertSecurityDescriptorToStringSecurityDescriptorW")
        try:
            return text.value
        finally:
            w.k32.LocalFree(text)
    finally:
        w.k32.LocalFree(descriptor)


def create_server(name: str) -> int:
    """A server instance of `name` with the mod's flags and a DACL of one ACE for this user,
    the fake's; PipeError when the name exists (FILE_FLAG_FIRST_PIPE_INSTANCE)."""
    w = api()
    descriptor = ctypes.c_void_p()
    sddl = f"D:P(A;;GA;;;{current_user_sid()})"
    if not w.adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, SDDL_REVISION_1, ctypes.byref(descriptor), None
    ):
        raise fail("ConvertStringSecurityDescriptorToSecurityDescriptorW")
    try:
        attributes = w.SECURITY_ATTRIBUTES(
            ctypes.sizeof(w.SECURITY_ATTRIBUTES), descriptor.value, False
        )
        handle = w.k32.CreateNamedPipeW(
            name, OPEN_MODE, PIPE_MODE, 1, BUFFER_BYTES, BUFFER_BYTES, 0, ctypes.byref(attributes)
        )
        if handle == w.invalid:
            raise fail(f"CreateNamedPipeW {name}")
        return handle
    finally:
        w.k32.LocalFree(descriptor)


def second_instance(name: str) -> int:
    """Try to create another server instance of `name` with the mod's flags: the Windows error
    that refused it (ERROR_ACCESS_DENIED from FILE_FLAG_FIRST_PIPE_INSTANCE, ERROR_PIPE_BUSY
    from the one-instance limit), or 0 when it was created (then closed at once)."""
    w = api()
    handle = w.k32.CreateNamedPipeW(name, OPEN_MODE, PIPE_MODE, 1, 1024, 1024, 0, None)
    if handle == w.invalid:
        return ctypes.get_last_error()
    w.k32.CloseHandle(handle)
    return 0


def accept(handle: int) -> Pipe | None:
    """Wait for a client on a server instance: its Pipe, or None when it left before it was
    served (the pipe is disconnected and can be served again)."""
    w = api()
    overlapped = w.OVERLAPPED()
    overlapped.hEvent = w.k32.CreateEventW(None, True, False, None)
    try:
        if not w.k32.ConnectNamedPipe(handle, ctypes.byref(overlapped)):
            error = ctypes.get_last_error()
            if error == ERROR_IO_PENDING:
                moved = w.wintypes.DWORD()
                if not w.k32.GetOverlappedResult(
                    handle, ctypes.byref(overlapped), ctypes.byref(moved), True
                ):
                    w.k32.DisconnectNamedPipe(handle)
                    return None
            elif error == ERROR_NO_DATA:
                w.k32.DisconnectNamedPipe(handle)
                return None
            elif error != ERROR_PIPE_CONNECTED:
                raise fail("ConnectNamedPipe", error)
        return ServerEnd(handle)
    finally:
        w.k32.CloseHandle(overlapped.hEvent)


class ServerEnd(Pipe):
    """A connected server instance: close() disconnects the client and keeps the instance."""

    def _release(self) -> None:
        api().k32.DisconnectNamedPipe(self.handle)
