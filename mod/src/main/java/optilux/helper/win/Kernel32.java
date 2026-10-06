package optilux.helper.win;

import com.sun.jna.Library;
import com.sun.jna.Pointer;
import com.sun.jna.platform.win32.WinNT.HANDLE;
import com.sun.jna.ptr.IntByReference;

/**
 * The mod's own kernel32 binding over the JNA the game ships, for what jna-platform 5.17.0 lacks
 * or binds unsafely (docs/plans/m1.md P12): QueryPerformanceCounter and QueryPerformanceFrequency;
 * GetOverlappedResult and CancelIoEx; and ReadFile, WriteFile and ConnectNamedPipe with raw
 * pointers. jna-platform passes a byte[] buffer and an OVERLAPPED Structure, which JNA copies
 * around each call: an overlapped operation outlives the call, so its buffer and OVERLAPPED must
 * be native memory that stays put until GetOverlappedResult says it completed.
 */
public interface Kernel32 extends Library {
    boolean QueryPerformanceCounter(long[] count);

    boolean QueryPerformanceFrequency(long[] frequency);

    boolean ReadFile(HANDLE file, Pointer buffer, int toRead, IntByReference read, Pointer overlapped);

    boolean WriteFile(HANDLE file, Pointer buffer, int toWrite, IntByReference written,
        Pointer overlapped);

    boolean ConnectNamedPipe(HANDLE pipe, Pointer overlapped);

    boolean GetOverlappedResult(HANDLE file, Pointer overlapped, IntByReference transferred,
        boolean wait);

    boolean CancelIoEx(HANDLE file, Pointer overlapped);
}
