package optilux.helper.win;

import com.sun.jna.Memory;
import com.sun.jna.Native;
import com.sun.jna.Pointer;
import com.sun.jna.platform.win32.WinBase;
import com.sun.jna.platform.win32.WinDef;
import com.sun.jna.platform.win32.WinError;
import com.sun.jna.platform.win32.WinNT;
import com.sun.jna.platform.win32.WinNT.HANDLE;
import com.sun.jna.ptr.IntByReference;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicLong;
import optilux.helper.core.LineFramer;
import optilux.helper.core.Protocol;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The pipe server on its own I/O thread (docs/mod.md#4-architecture: reads and writes only).
 * One instance of a byte-mode named pipe, created with FILE_FLAG_FIRST_PIPE_INSTANCE (a squatter
 * that took the name first makes the creation fail), PIPE_REJECT_REMOTE_CLIENTS and the user-only
 * DACL of {@link Security}; one client at a time, whose process owner must be this user. The
 * handle is overlapped: a synchronous pipe handle serializes every I/O on it, so a pending read
 * would block each write. The thread waits on the read's event and the outbox's event together,
 * so a response never waits for the client's next line. A client that connects and leaves before
 * the accept is disconnected and the pipe served again (ALC's ERROR_NO_DATA bug); errors are read
 * through Native.getLastError right after each call (ALC read the wrong one).
 */
public final class PipeServer implements Runnable {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    private static final com.sun.jna.platform.win32.Kernel32 K32 =
        com.sun.jna.platform.win32.Kernel32.INSTANCE;
    /** Absent from jna-platform 5.17.0 (docs/plans/m1.md P12); winbase.h's value. */
    public static final int FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000;
    public static final int OPEN_MODE = WinBase.PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE
        | WinNT.FILE_FLAG_OVERLAPPED;
    public static final int PIPE_MODE = WinBase.PIPE_TYPE_BYTE | WinBase.PIPE_READMODE_BYTE
        | WinBase.PIPE_WAIT | WinBase.PIPE_REJECT_REMOTE_CLIENTS;
    /** One client at a time (docs/mod-protocol.md#transport). */
    public static final int INSTANCES = 1;
    // The kernel's buffer quotas, advisory; a read takes at most READ_BYTES at once.
    private static final int BUFFER_BYTES = 64 * 1024;
    private static final int READ_BYTES = 64 * 1024;
    /** A client that reads nothing for this long is dropped, so the thread never hangs on it. */
    private static final int WRITE_TIMEOUT_MS = 10_000;
    // A failed accept is retried after this pause, so a persistent error cannot spin the thread.
    private static final long RETRY_MS = 250;

    private final String name;
    private final Protocol protocol;
    private final Kernel32 io;
    private final ConcurrentLinkedQueue<Outgoing> outbox = new ConcurrentLinkedQueue<>();
    private final HANDLE outboxEvent;
    private final AtomicLong serial = new AtomicLong();
    private final Overlapped readOverlapped = new Overlapped();
    private final Overlapped writeOverlapped = new Overlapped();
    private final Overlapped connectOverlapped = new Overlapped();
    private final Memory readBuffer = new Memory(READ_BYTES);
    private final LineFramer framer;

    private record Outgoing(long connection, byte[] bytes, Runnable after) {
    }

    /**
     * The OVERLAPPED structure as raw native memory with its own manual-reset event: a JNA
     * Structure would be rewritten from its Java fields at each call, over the kernel's status.
     */
    private static final class Overlapped {
        // Internal and InternalHigh (pointer-sized), Offset and OffsetHigh, then hEvent.
        static final int EVENT_OFFSET = 2 * Native.POINTER_SIZE + 8;
        final Memory memory = new Memory(EVENT_OFFSET + Native.POINTER_SIZE);
        final HANDLE event = K32.CreateEvent(null, true, false, null);

        Overlapped() {
            if (event == null) {
                throw new IllegalStateException("CreateEvent failed: error " + Native.getLastError());
            }
            memory.clear();
            memory.setPointer(EVENT_OFFSET, event.getPointer());
        }

        /** Zero the status and offsets before an operation; the event stays. */
        Pointer fresh() {
            memory.clear(EVENT_OFFSET);
            return memory;
        }
    }

    public PipeServer(String name, Protocol protocol, Kernel32 io) {
        this.name = name;
        this.protocol = protocol;
        this.io = io;
        this.framer = new LineFramer(new LineFramer.Sink() {
            @Override
            public void line(String text) {
                protocol.line(text);
            }

            @Override
            public void refused(String code, String message) {
                protocol.refused(code, message);
            }
        });
        this.outboxEvent = K32.CreateEvent(null, false, false, null);
        if (outboxEvent == null) {
            throw new IllegalStateException("CreateEvent failed: error " + Native.getLastError());
        }
    }

    /** Create the pipe: one instance, first instance only, local clients, the user-only DACL. */
    public HANDLE create() {
        Security.UserOnly security = Security.userOnly();
        HANDLE pipe = K32.CreateNamedPipe(name, OPEN_MODE, PIPE_MODE, INSTANCES, BUFFER_BYTES,
            BUFFER_BYTES, 0, security.attributes());
        int error = Native.getLastError();
        security.keepAlive();
        if (pipe == null || WinBase.INVALID_HANDLE_VALUE.equals(pipe)) {
            throw new IllegalStateException("CreateNamedPipe failed: error " + error
                + (error == WinError.ERROR_ACCESS_DENIED
                    ? " (the name exists: another process created it first)" : ""));
        }
        return pipe;
    }

    @Override
    public void run() {
        HANDLE pipe;
        try {
            pipe = create();
        } catch (RuntimeException error) {
            LOG.error("optilux-helper: pipe {}: {}; no client can connect", name, error.getMessage());
            return;
        }
        LOG.info("optilux-helper: pipe {} open: one instance, local clients, DACL with one ACE "
            + "for this user", name);
        while (true) {
            try {
                Integer client = accept(pipe);
                if (client == null) {
                    continue;
                }
                if (!Security.sameUser(client)) {
                    LOG.warn("optilux-helper: pipe client pid {} refused: not this user", client);
                    K32.DisconnectNamedPipe(pipe);
                    continue;
                }
                LOG.info("optilux-helper: pipe client pid {} connected", client);
                serve(pipe);
                LOG.info("optilux-helper: pipe client pid {} disconnected", client);
            } catch (RuntimeException | Error error) {
                // An Error too (a worker that cannot start): the pipe thread never dies of one
                // (docs/mod.md#4-architecture).
                LOG.error("optilux-helper: pipe I/O failed; serving again", error);
                K32.DisconnectNamedPipe(pipe);
                pause();
            }
        }
    }

    /** Wait for a client; its pid, or null when it left first or the accept failed. */
    private Integer accept(HANDLE pipe) {
        Pointer overlapped = connectOverlapped.fresh();
        if (!io.ConnectNamedPipe(pipe, overlapped)) {
            int error = Native.getLastError();
            if (error == WinError.ERROR_IO_PENDING) {
                // Lines answered after a disconnect still run their `after` (quit's stop).
                HANDLE[] events = {connectOverlapped.event, outboxEvent};
                while (K32.WaitForMultipleObjects(events.length, events, false, WinBase.INFINITE)
                    == WinBase.WAIT_OBJECT_0 + 1) {
                    drain(null, 0);
                }
                IntByReference ignored = new IntByReference();
                if (!io.GetOverlappedResult(pipe, overlapped, ignored, false)) {
                    LOG.info("optilux-helper: pipe accept ended with error {}; serving again",
                        Native.getLastError());
                    K32.DisconnectNamedPipe(pipe);
                    return null;
                }
            } else if (error == WinError.ERROR_NO_DATA) {
                K32.DisconnectNamedPipe(pipe);
                return null;
            } else if (error != WinError.ERROR_PIPE_CONNECTED) {
                LOG.warn("optilux-helper: ConnectNamedPipe failed: error {}; serving again", error);
                K32.DisconnectNamedPipe(pipe);
                pause();
                return null;
            }
        }
        WinDef.ULONGByReference pid = new WinDef.ULONGByReference();
        if (!K32.GetNamedPipeClientProcessId(pipe, pid)) {
            LOG.warn("optilux-helper: GetNamedPipeClientProcessId failed: error {}",
                Native.getLastError());
            K32.DisconnectNamedPipe(pipe);
            return null;
        }
        return pid.getValue().intValue();
    }

    /** One connection: reads feed the framer, the outbox is written as it fills. */
    private void serve(HANDLE pipe) {
        long connection = serial.incrementAndGet();
        framer.reset();
        protocol.connected((line, after) -> {
            outbox.add(new Outgoing(connection, (line + "\n").getBytes(StandardCharsets.UTF_8), after));
            K32.SetEvent(outboxEvent);
        });
        HANDLE[] events = {readOverlapped.event, outboxEvent};
        boolean reading = false;
        try {
            while (true) {
                if (!reading) {
                    if (!io.ReadFile(pipe, readBuffer, READ_BYTES, null, readOverlapped.fresh())) {
                        int error = Native.getLastError();
                        if (error != WinError.ERROR_IO_PENDING) {
                            ended("ReadFile", error);
                            return;
                        }
                    }
                    reading = true;
                }
                int woke = K32.WaitForMultipleObjects(events.length, events, false, WinBase.INFINITE);
                if (woke == WinBase.WAIT_OBJECT_0) {
                    reading = false;
                    IntByReference read = new IntByReference();
                    if (!io.GetOverlappedResult(pipe, readOverlapped.memory, read, false)) {
                        ended("read", Native.getLastError());
                        return;
                    }
                    byte[] bytes = readBuffer.getByteArray(0, read.getValue());
                    framer.feed(bytes, 0, bytes.length);
                    // A client that keeps writing would win every wait (the lowest index does).
                    if (!outbox.isEmpty() && !drain(pipe, connection)) {
                        return;
                    }
                } else if (woke == WinBase.WAIT_OBJECT_0 + 1) {
                    if (!drain(pipe, connection)) {
                        return;
                    }
                } else {
                    throw new IllegalStateException("WaitForMultipleObjects returned " + woke
                        + ", error " + Native.getLastError());
                }
            }
        } finally {
            if (reading) {
                io.CancelIoEx(pipe, readOverlapped.memory);
                // Wait until the kernel is done with the buffer and the OVERLAPPED.
                io.GetOverlappedResult(pipe, readOverlapped.memory, new IntByReference(), true);
            }
            protocol.disconnected();
            K32.DisconnectNamedPipe(pipe);
            drain(null, connection);
        }
    }

    /**
     * Write the queued lines of this connection; lines of an older one are dropped. Every line's
     * `after` runs. False when the client is gone or stopped reading. With no pipe, only drop.
     */
    private boolean drain(HANDLE pipe, long connection) {
        boolean open = pipe != null;
        Outgoing next;
        while ((next = outbox.poll()) != null) {
            try {
                if (open && next.connection() == connection && !write(pipe, next.bytes())) {
                    open = false;
                }
            } finally {
                runAfter(next);
            }
        }
        return open;
    }

    private static void runAfter(Outgoing outgoing) {
        try {
            outgoing.after().run();
        } catch (RuntimeException error) {
            LOG.warn("optilux-helper: an after-answer action failed", error);
        }
    }

    private boolean write(HANDLE pipe, byte[] bytes) {
        Memory buffer = new Memory(bytes.length);
        try {
            return write(pipe, buffer, bytes);
        } finally {
            // The kernel may use the buffer until the write completed or its cancel did.
            java.lang.ref.Reference.reachabilityFence(buffer);
        }
    }

    private boolean write(HANDLE pipe, Memory buffer, byte[] bytes) {
        buffer.write(0, bytes, 0, bytes.length);
        Pointer overlapped = writeOverlapped.fresh();
        if (!io.WriteFile(pipe, buffer, bytes.length, null, overlapped)) {
            int error = Native.getLastError();
            if (error != WinError.ERROR_IO_PENDING) {
                ended("WriteFile", error);
                return false;
            }
            if (K32.WaitForSingleObject(writeOverlapped.event, WRITE_TIMEOUT_MS) != WinBase.WAIT_OBJECT_0) {
                io.CancelIoEx(pipe, overlapped);
                io.GetOverlappedResult(pipe, overlapped, new IntByReference(), true);
                LOG.warn("optilux-helper: pipe client read nothing for {} ms; dropped",
                    WRITE_TIMEOUT_MS);
                return false;
            }
        }
        IntByReference written = new IntByReference();
        if (!io.GetOverlappedResult(pipe, overlapped, written, false)) {
            ended("write", Native.getLastError());
            return false;
        }
        if (written.getValue() != bytes.length) {
            LOG.warn("optilux-helper: pipe wrote {} of {} bytes; dropped", written.getValue(),
                bytes.length);
            return false;
        }
        return true;
    }

    private static void ended(String what, int error) {
        if (error != WinError.ERROR_BROKEN_PIPE && error != WinError.ERROR_PIPE_NOT_CONNECTED
            && error != WinError.ERROR_NO_DATA) {
            LOG.warn("optilux-helper: pipe {} failed: error {}", what, error);
        }
    }

    private static void pause() {
        try {
            Thread.sleep(RETRY_MS);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
    }
}
