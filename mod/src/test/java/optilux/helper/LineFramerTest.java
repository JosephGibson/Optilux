package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import optilux.helper.core.Errors;
import optilux.helper.core.LineFramer;
import org.junit.jupiter.api.Test;

/** Lines from the byte stream (docs/mod-protocol.md#transport): \n, \r dropped, 1 MiB, UTF-8. */
class LineFramerTest {
    private final List<String> seen = new ArrayList<>();
    private final LineFramer framer = new LineFramer(new LineFramer.Sink() {
        @Override
        public void line(String text) {
            seen.add("line:" + text);
        }

        @Override
        public void refused(String code, String message) {
            seen.add(code);
        }
    });

    private void feed(String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        framer.feed(bytes, 0, bytes.length);
    }

    @Test
    void linesSplitAnywhereAndOneTrailingCrDropped() {
        feed("{\"a\":1}\r\n{\"b\"");
        feed(":2}\n\n");
        feed("x\r\r\n");
        assertEquals(List.of("line:{\"a\":1}", "line:{\"b\":2}", "line:", "line:x\r"), seen);
    }

    @Test
    void anOverlongLineIsRefusedAtOnceAndSkippedToItsEnd() {
        byte[] full = new byte[LineFramer.MAX_LINE];
        Arrays.fill(full, (byte) 'a');
        framer.feed(full, 0, full.length);
        assertEquals(List.of(), seen, "exactly MAX_LINE bytes is still a line");
        feed("\n");
        assertEquals(1, seen.size());
        assertEquals(LineFramer.MAX_LINE + 5, seen.get(0).length());
        seen.clear();
        framer.feed(full, 0, full.length);
        feed("b");
        assertEquals(List.of(Errors.LINE_TOO_LONG), seen, "refused before its \\n arrived");
        framer.feed(full, 0, full.length);
        feed("tail\n{\"ok\":1}\n");
        assertEquals(List.of(Errors.LINE_TOO_LONG, "line:{\"ok\":1}"), seen);
    }

    @Test
    void aLineThatIsNotUtf8IsRefused() {
        byte[] bad = {'{', (byte) 0xff, '}', '\n', (byte) 0xc3, (byte) 0xa9, '\n', (byte) 0xed,
            (byte) 0xa0, (byte) 0x80, '\n'};
        framer.feed(bad, 0, bad.length);
        assertEquals(List.of(Errors.BAD_ENCODING, "line:é", Errors.BAD_ENCODING), seen);
    }

    @Test
    void aResetDropsAPartialLine() {
        feed("{\"half\"");
        framer.reset();
        feed("{}\n");
        assertEquals(List.of("line:{}"), seen);
    }
}
