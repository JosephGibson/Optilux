package optilux.helper.core;

import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.StandardCharsets;

/**
 * What one shader reload's outcome answers (docs/mod-protocol.md#errors, roadmap.md F5). On Iris
 * 1.11.7 a failed load in a world never reaches getStoredError: Iris.handleException sends a chat
 * message and the loader falls back to vanilla rendering, so the Iris adapter hooks handleException
 * and reads isFallback after Iris.reload returns. A hooked exception answers iris-compile-error
 * with its message cut at {@link #MESSAGE_BYTES}; a fallback without one, or a reload that threw,
 * answers failed; otherwise the reload succeeded.
 */
public final class ReloadOutcome {
    /** Iris's error is cut at 16 KiB of UTF-8 (docs/mod-protocol.md#errors). */
    public static final int MESSAGE_BYTES = 16 * 1024;

    private ReloadOutcome() {
    }

    /**
     * The refusal a reload answers, or null when it succeeded. `hooked` is the exception Iris
     * handed to handleException during the reload, `thrown` what Iris.reload itself threw,
     * `fallback` Iris.isFallback() after it, `pack` the pack Iris names.
     */
    public static Errors.Refused of(Throwable hooked, Throwable thrown, boolean fallback, String pack) {
        if (hooked != null) {
            return new Errors.Refused(Errors.IRIS_COMPILE_ERROR, cut(describe(hooked), MESSAGE_BYTES));
        }
        if (thrown != null) {
            return new Errors.Refused(Errors.FAILED, cut("Iris.reload threw " + describe(thrown),
                MESSAGE_BYTES));
        }
        if (fallback) {
            return new Errors.Refused(Errors.FAILED, "Iris fell back to vanilla rendering: pack "
                + pack + " did not load; latest.log names why");
        }
        return null;
    }

    static String describe(Throwable error) {
        String message = error.getMessage();
        return error.getClass().getSimpleName() + (message == null ? "" : ": " + message);
    }

    /** `text` cut to at most `bytes` bytes of UTF-8, never inside a character. */
    public static String cut(String text, int bytes) {
        CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder();
        ByteBuffer out = ByteBuffer.allocate(bytes);
        CharBuffer in = CharBuffer.wrap(text);
        encoder.encode(in, out, true);
        return text.substring(0, in.position());
    }
}
