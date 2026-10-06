package optilux.helper.win;

import com.sun.jna.Native;
import com.sun.jna.platform.win32.Advapi32;
import com.sun.jna.platform.win32.WinBase;
import com.sun.jna.platform.win32.WinDef;
import com.sun.jna.platform.win32.WinError;
import com.sun.jna.platform.win32.WinNT;
import com.sun.jna.platform.win32.WinNT.HANDLE;
import com.sun.jna.ptr.IntByReference;
import java.util.Arrays;

/**
 * The pipe's security (docs/mod.md#5-safety, docs/plans/m1.md D21): a security descriptor whose
 * DACL holds one ACE, GENERIC_ALL for this process token's user SID, built with jna-platform's
 * Advapi32; and the owner check of a connecting client, its process token's user against ours.
 * ALC's default descriptor let every local account read the pipe.
 */
public final class Security {
    private static final com.sun.jna.platform.win32.Kernel32 K32 =
        com.sun.jna.platform.win32.Kernel32.INSTANCE;
    private static final Advapi32 ADVAPI32 = Advapi32.INSTANCE;
    // ACCESS_ALLOWED_ACE: a 4-byte ACE_HEADER and the 4-byte mask, then the SID.
    private static final int ACL_HEADER = 8;
    private static final int ACE_FIXED = 8;
    // SECURITY_DESCRIPTOR in absolute form is 40 bytes on x64 (SECURITY_DESCRIPTOR_MIN_LENGTH).
    private static final int DESCRIPTOR_BYTES = 64;
    // Opens another user's elevated process too, never more than its token's identity.
    private static final int PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;

    private Security() {
    }

    /**
     * SECURITY_ATTRIBUTES for CreateNamedPipe and the native memory it points to: the ACL and the
     * descriptor are held here, because the descriptor keeps only the ACL's address.
     */
    public static final class UserOnly {
        private final WinNT.PSID sid;
        private final WinNT.ACL acl;
        private final WinNT.SECURITY_DESCRIPTOR descriptor;
        private final WinBase.SECURITY_ATTRIBUTES attributes;

        UserOnly(byte[] user) {
            sid = new WinNT.PSID(user);
            int size = (ACL_HEADER + ACE_FIXED + user.length + 3) & ~3;
            acl = new WinNT.ACL(size);
            check(ADVAPI32.InitializeAcl(acl, size, WinNT.ACL_REVISION), "InitializeAcl");
            check(ADVAPI32.AddAccessAllowedAce(acl, WinNT.ACL_REVISION, WinNT.GENERIC_ALL, sid),
                "AddAccessAllowedAce");
            descriptor = new WinNT.SECURITY_DESCRIPTOR(DESCRIPTOR_BYTES);
            check(ADVAPI32.InitializeSecurityDescriptor(descriptor,
                WinNT.SECURITY_DESCRIPTOR_REVISION), "InitializeSecurityDescriptor");
            check(ADVAPI32.SetSecurityDescriptorDacl(descriptor, true, acl, false),
                "SetSecurityDescriptorDacl");
            attributes = new WinBase.SECURITY_ATTRIBUTES();
            attributes.dwLength = new WinDef.DWORD(attributes.size());
            attributes.lpSecurityDescriptor = descriptor.getPointer();
            attributes.bInheritHandle = false;
        }

        public WinBase.SECURITY_ATTRIBUTES attributes() {
            return attributes;
        }

        /** The ACEs the DACL holds, read back from its native memory. */
        public int aceCount() {
            acl.read();
            return acl.AceCount;
        }

        /** Keep the native memory alive until the pipe is created. */
        public void keepAlive() {
            java.lang.ref.Reference.reachabilityFence(sid);
            java.lang.ref.Reference.reachabilityFence(acl);
            java.lang.ref.Reference.reachabilityFence(descriptor);
        }
    }

    public static UserOnly userOnly() {
        return new UserOnly(currentUser());
    }

    /** This process token's user SID. */
    public static byte[] currentUser() {
        return tokenUser(K32.GetCurrentProcess());
    }

    /** Whether a process runs as this process's user; false when it cannot be opened. */
    public static boolean sameUser(int pid) {
        HANDLE process = K32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid);
        if (process == null) {
            return false;
        }
        try {
            return Arrays.equals(tokenUser(process), currentUser());
        } catch (IllegalStateException error) {
            return false;
        } finally {
            K32.CloseHandle(process);
        }
    }

    private static byte[] tokenUser(HANDLE process) {
        WinNT.HANDLEByReference token = new WinNT.HANDLEByReference();
        check(ADVAPI32.OpenProcessToken(process, WinNT.TOKEN_QUERY, token), "OpenProcessToken");
        try {
            IntByReference needed = new IntByReference();
            if (!ADVAPI32.GetTokenInformation(token.getValue(),
                WinNT.TOKEN_INFORMATION_CLASS.TokenUser, null, 0, needed)) {
                int error = Native.getLastError();
                if (error != WinError.ERROR_INSUFFICIENT_BUFFER) {
                    throw new IllegalStateException("GetTokenInformation failed: error " + error);
                }
            }
            WinNT.TOKEN_USER user = new WinNT.TOKEN_USER(needed.getValue());
            check(ADVAPI32.GetTokenInformation(token.getValue(),
                WinNT.TOKEN_INFORMATION_CLASS.TokenUser, user, needed.getValue(), needed),
                "GetTokenInformation");
            return user.User.Sid.getBytes();
        } finally {
            K32.CloseHandle(token.getValue());
        }
    }

    private static void check(boolean ok, String call) {
        if (!ok) {
            throw new IllegalStateException(call + " failed: error " + Native.getLastError());
        }
    }
}
