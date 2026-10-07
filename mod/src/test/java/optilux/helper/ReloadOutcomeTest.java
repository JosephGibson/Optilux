package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import optilux.helper.core.Errors;
import optilux.helper.core.ReloadOutcome;
import org.junit.jupiter.api.Test;

/** A reload's outcomes mapped to answers (roadmap.md F5, docs/mod-protocol.md#errors). */
class ReloadOutcomeTest {
    @Test
    void aReloadThatLoadedAnswersOk() {
        assertNull(ReloadOutcome.of(null, null, false, "ComplementaryUnbound_r5.9.3.zip"));
    }

    @Test
    void aHookedExceptionIsACompileErrorWithItsMessage() {
        // Iris's ShaderCompileException says "<file>: <error>"; a RuntimeException stands in.
        Errors.Refused refused = ReloadOutcome.of(
            new RuntimeException("composite1.fsh: 0(12) : error C0000: syntax error"), null, true,
            "broken.zip");
        assertEquals(Errors.IRIS_COMPILE_ERROR, refused.code());
        assertEquals("RuntimeException: composite1.fsh: 0(12) : error C0000: syntax error",
            refused.getMessage());
    }

    @Test
    void aFallbackWithoutAnExceptionFails() {
        Errors.Refused refused = ReloadOutcome.of(null, null, true, "missing.zip");
        assertEquals(Errors.FAILED, refused.code());
        assertTrue(refused.getMessage().contains("missing.zip"), refused.getMessage());
    }

    @Test
    void aReloadThatThrewFailsAndAHookedErrorWins() {
        Errors.Refused refused = ReloadOutcome.of(null, new IOException("disk"), false, "p.zip");
        assertEquals(Errors.FAILED, refused.code());
        assertEquals("Iris.reload threw IOException: disk", refused.getMessage());
        refused = ReloadOutcome.of(new IllegalStateException("compile"), new IOException("disk"),
            true, "p.zip");
        assertEquals(Errors.IRIS_COMPILE_ERROR, refused.code());
    }

    @Test
    void theMessageIsCutAt16KiBOfUtf8NeverInsideACharacter() {
        String log = "e".repeat(ReloadOutcome.MESSAGE_BYTES);
        Errors.Refused refused = ReloadOutcome.of(new RuntimeException(log), null, true, "p.zip");
        assertEquals(ReloadOutcome.MESSAGE_BYTES,
            refused.getMessage().getBytes(StandardCharsets.UTF_8).length);
        assertEquals("abc", ReloadOutcome.cut("abc", 10));
        // "é" is two bytes: four bytes hold "aé" and one byte of the next "é", which is left out.
        assertEquals("aé", ReloadOutcome.cut("aéé", 4));
        // A surrogate pair is four bytes and stays whole.
        assertEquals("a", ReloadOutcome.cut("a😀", 4));
        assertEquals("a😀", ReloadOutcome.cut("a😀b", 5));
    }
}
