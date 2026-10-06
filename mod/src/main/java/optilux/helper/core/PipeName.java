package optilux.helper.core;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/**
 * The pipe's name (docs/mod-protocol.md#transport): \\.\pipe\optilux- and the first 32 hex digits
 * of SHA-256("optilux-pipe:" + token). Only a holder of the token finds it, and the name tells
 * nothing of the token; the harness derives the same name (optilux/modclient.py).
 */
public final class PipeName {
    public static final String PREFIX = "\\\\.\\pipe\\optilux-";
    static final String SALT = "optilux-pipe:";
    static final int HEX_DIGITS = 32;

    private PipeName() {
    }

    public static String of(String token) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest((SALT + token).getBytes(StandardCharsets.UTF_8));
            return PREFIX + HexFormat.of().formatHex(digest).substring(0, HEX_DIGITS);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("no SHA-256 in this JVM", error);
        }
    }
}
