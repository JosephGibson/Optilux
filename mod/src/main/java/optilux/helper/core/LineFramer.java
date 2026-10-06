package optilux.helper.core;

import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

/**
 * The pipe's byte stream cut into lines (docs/mod-protocol.md#transport): UTF-8, one value per
 * line ended by \n, one trailing \r dropped, at most {@link #MAX_LINE} bytes before the \n. A line
 * that grows past the cap is refused the moment it does, never at a timeout (ALC's malformed line
 * waited for one), and its rest is skipped up to the next \n; a line that is not UTF-8 is refused
 * whole. One framer per connection, fed by the pipe I/O thread only.
 */
public final class LineFramer {
    public static final int MAX_LINE = 1 << 20;

    /** Where lines and refusals go; called on the feeding thread. */
    public interface Sink {
        void line(String text);

        void refused(String code, String message);
    }

    private final Sink sink;
    private final byte[] buffer = new byte[MAX_LINE];
    private final CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
    private int length;
    private boolean skipping;
    private long lines;

    public LineFramer(Sink sink) {
        this.sink = sink;
    }

    /** Forget a partial line: a new connection starts clean. */
    public void reset() {
        length = 0;
        skipping = false;
        lines = 0;
    }

    public void feed(byte[] data, int offset, int count) {
        for (int i = offset; i < offset + count; i++) {
            byte b = data[i];
            if (b == '\n') {
                if (skipping) {
                    skipping = false;
                } else {
                    emit();
                }
                length = 0;
                lines++;
            } else if (!skipping) {
                if (length == MAX_LINE) {
                    skipping = true;
                    length = 0;
                    sink.refused(Errors.LINE_TOO_LONG,
                        "line " + (lines + 1) + " passed " + MAX_LINE + " bytes; it is skipped up to its \\n");
                } else {
                    buffer[length++] = b;
                }
            }
        }
    }

    private void emit() {
        int end = length > 0 && buffer[length - 1] == '\r' ? length - 1 : length;
        CharBuffer text;
        try {
            decoder.reset();
            text = decoder.decode(ByteBuffer.wrap(buffer, 0, end));
        } catch (CharacterCodingException error) {
            sink.refused(Errors.BAD_ENCODING, "line " + (lines + 1) + " is not UTF-8");
            return;
        }
        sink.line(text.toString());
    }
}
