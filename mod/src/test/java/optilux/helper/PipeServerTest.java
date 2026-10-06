package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.sun.jna.Native;
import com.sun.jna.platform.win32.AccCtrl;
import com.sun.jna.platform.win32.Advapi32;
import com.sun.jna.platform.win32.Kernel32;
import com.sun.jna.platform.win32.WinBase;
import com.sun.jna.platform.win32.WinDef;
import com.sun.jna.platform.win32.WinError;
import com.sun.jna.platform.win32.WinNT;
import com.sun.jna.platform.win32.WinNT.HANDLE;
import com.sun.jna.ptr.IntByReference;
import com.sun.jna.ptr.PointerByReference;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.Executors;
import optilux.helper.core.Errors;
import optilux.helper.core.PipeName;
import optilux.helper.core.Protocol;
import optilux.helper.core.State;
import optilux.helper.win.PipeServer;
import optilux.helper.win.Qpc;
import optilux.helper.win.Security;
import org.junit.jupiter.api.Test;

/**
 * The pipe server over a real named pipe on this machine (the mod's tests run only here, D19):
 * the DACL read back from the pipe holds one ACE for this user (D21), the server pid, a second
 * instance refused, a client leaving before it is served (ALC's ERROR_NO_DATA), answers at once,
 * and a reconnect resumed.
 */
class PipeServerTest {
    private static final Kernel32 K32 = Kernel32.INSTANCE;

    @Test
    @SuppressWarnings("unchecked")
    void aRealPipe() throws Exception {
        byte[] random = new byte[32];
        new SecureRandom().nextBytes(random);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(random);
        String name = PipeName.of(token);
        var timers = Executors.newSingleThreadScheduledExecutor();
        Protocol protocol = new Protocol(Wire.COMMANDS, token, Map.of("frames.index", r -> Map.of()),
            () -> ProtocolTest.FACTS, new Protocol.Stamps() {
                @Override
                public long frameIndex() {
                    return 1;
                }

                @Override
                public Long sinceReload() {
                    return null;
                }

                @Override
                public long qpcNs() {
                    return 2;
                }
            }, new State(timers, Duration.ofSeconds(10)), Executors.newCachedThreadPool(), timers);
        Thread thread = new Thread(new PipeServer(name, protocol, Qpc.kernel32()), "optilux-pipe-test");
        thread.setDaemon(true);
        thread.start();

        // Clients that leave before or while being served do not stop the server.
        for (int i = 0; i < 3; i++) {
            K32.CloseHandle(open(name));
        }
        HANDLE client = open(name);
        try {
            PointerByReference dacl = new PointerByReference();
            PointerByReference descriptor = new PointerByReference();
            assertEquals(0, Advapi32.INSTANCE.GetSecurityInfo(client,
                AccCtrl.SE_OBJECT_TYPE.SE_KERNEL_OBJECT, WinNT.DACL_SECURITY_INFORMATION, null, null,
                dacl, null, descriptor));
            WinNT.ACL acl = new WinNT.ACL(dacl.getValue());
            assertEquals(1, acl.AceCount, "the DACL holds one ACE");
            WinNT.ACE_HEADER ace = acl.getACEs()[0];
            assertEquals(WinNT.ACCESS_ALLOWED_ACE_TYPE, ace.AceType);
            assertArrayEquals(Security.currentUser(),
                ((WinNT.ACCESS_ALLOWED_ACE) ace).getSID().getBytes(), "the ACE is this user's");
            K32.LocalFree(descriptor.getValue());

            WinDef.ULONGByReference server = new WinDef.ULONGByReference();
            assertTrue(K32.GetNamedPipeServerProcessId(client, server));
            assertEquals(ProcessHandle.current().pid(), server.getValue().longValue());

            HANDLE second = K32.CreateNamedPipe(name, PipeServer.OPEN_MODE, PipeServer.PIPE_MODE, 1,
                1024, 1024, 0, null);
            int error = Native.getLastError();
            assertEquals(WinBase.INVALID_HANDLE_VALUE, second, "a second instance was created");
            assertTrue(error == WinError.ERROR_ACCESS_DENIED || error == WinError.ERROR_PIPE_BUSY,
                "error " + error);

            write(client, "{\"id\":1,\"cmd\":\"frames.index\",\"args\":{}}\n");
            assertEquals(Errors.UNAUTHENTICATED, code(Wire.parse(readLine(client))));
            write(client, "not json\r\n");
            assertEquals(Errors.BAD_JSON, code(Wire.parse(readLine(client))));
            write(client, "{\"id\":\"h\",\"cmd\":\"hello\",\"args\":{\"token\":\"" + token + "\"}}\n");
            Map<String, Object> hello = Wire.parse(readLine(client));
            Wire.check("hello", hello);
            assertEquals(false, ((Map<String, Object>) hello.get("result")).get("resumed"));
            write(client, "{\"id\":2,\"cmd\":\"frames.index\",\"args\":{}}\n");
            Map<String, Object> index = Wire.parse(readLine(client));
            Wire.check("frames.index", index);
            assertEquals(true, index.get("ok"));
        } finally {
            K32.CloseHandle(client);
        }
        HANDLE again = open(name);
        try {
            write(again, "{\"id\":\"h\",\"cmd\":\"hello\",\"args\":{\"token\":\"" + token + "\"}}\n");
            Map<String, Object> hello = Wire.parse(readLine(again));
            assertEquals(true, ((Map<String, Object>) hello.get("result")).get("resumed"));
        } finally {
            K32.CloseHandle(again);
        }
    }

    @Test
    void aSquatterOnTheNameStopsTheServer() {
        byte[] random = new byte[32];
        new SecureRandom().nextBytes(random);
        String name = PipeName.of(Base64.getUrlEncoder().withoutPadding().encodeToString(random));
        assertTrue((PipeServer.OPEN_MODE & PipeServer.FILE_FLAG_FIRST_PIPE_INSTANCE) != 0);
        // Another process took the name first, open to more instances and to everyone.
        HANDLE squatter = K32.CreateNamedPipe(name, WinBase.PIPE_ACCESS_DUPLEX,
            WinBase.PIPE_TYPE_BYTE, WinBase.PIPE_UNLIMITED_INSTANCES, 1024, 1024, 0, null);
        assertTrue(!WinBase.INVALID_HANDLE_VALUE.equals(squatter), "error " + Native.getLastError());
        try {
            PipeServer server = new PipeServer(name, null, Qpc.kernel32());
            IllegalStateException refused =
                org.junit.jupiter.api.Assertions.assertThrows(IllegalStateException.class, server::create);
            assertTrue(refused.getMessage().startsWith("CreateNamedPipe failed: error "),
                refused.getMessage());
        } finally {
            K32.CloseHandle(squatter);
        }
    }

    @SuppressWarnings("unchecked")
    private static String code(Map<String, Object> answer) {
        return (String) ((Map<String, Object>) answer.get("error")).get("code");
    }

    /** Open the client end, retrying while the pipe is absent or serving another client. */
    private static HANDLE open(String name) throws InterruptedException {
        long until = System.nanoTime() + 5_000_000_000L;
        while (true) {
            HANDLE handle = K32.CreateFile(name, WinNT.GENERIC_READ | WinNT.GENERIC_WRITE, 0, null,
                WinNT.OPEN_EXISTING, 0, null);
            int error = Native.getLastError();
            if (!WinBase.INVALID_HANDLE_VALUE.equals(handle)) {
                return handle;
            }
            if (error != WinError.ERROR_FILE_NOT_FOUND && error != WinError.ERROR_PIPE_BUSY
                || System.nanoTime() > until) {
                throw new AssertionError("CreateFile " + name + " failed: error " + error);
            }
            Thread.sleep(10);
        }
    }

    private static void write(HANDLE pipe, String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        IntByReference written = new IntByReference();
        assertTrue(K32.WriteFile(pipe, bytes, bytes.length, written, null));
        assertEquals(bytes.length, written.getValue());
    }

    private static String readLine(HANDLE pipe) {
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        byte[] one = new byte[1];
        IntByReference read = new IntByReference();
        while (true) {
            assertTrue(K32.ReadFile(pipe, one, 1, read, null), "ReadFile: error " + Native.getLastError());
            if (read.getValue() == 1) {
                if (one[0] == '\n') {
                    return line.toString(StandardCharsets.UTF_8);
                }
                line.write(one[0]);
            }
        }
    }
}
