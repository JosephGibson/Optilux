package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import optilux.helper.core.Json;
import optilux.helper.core.PipeName;
import org.junit.jupiter.api.Test;

/** Strict JSON on the wire (docs/mod-protocol.md#envelope) and the pipe's name (#transport). */
class JsonTest {
    @Test
    void strictValuesWithNumbersKeptAsWritten() throws Json.Malformed {
        Object value = Json.parse("{\"id\": 1, \"x\": -0.5e3, \"s\": \"\\u00e9\\n\", \"b\": [true, null]}");
        Map<String, Object> expected = new LinkedHashMap<>();
        expected.put("id", new Json.Num("1"));
        expected.put("x", new Json.Num("-0.5e3"));
        expected.put("s", "\u00e9\n");
        expected.put("b", java.util.Arrays.asList(true, null));
        assertEquals(expected, value);
        assertEquals(true, new Json.Num("12").isInteger());
        assertEquals(false, new Json.Num("1.0").isInteger());
        assertEquals(false, new Json.Num("1e2").isInteger());
        assertEquals(-500.0, new Json.Num("-0.5e3").doubleValue());
    }

    @Test
    void everythingButStrictJsonIsRefused() {
        for (String bad : new String[] {
            "{'id': 1}", "{id: 1}", "{\"a\": 1,}", "[1,]", "{\"a\": NaN}", "{\"a\": Infinity}",
            "{\"a\": 01}", "{\"a\": .5}", "{\"a\": +1}", "{\"a\": 1} {}", "{\"a\": 1} x",
            "{\"a\": 1, \"a\": 2}", "/* c */ {}", "{\"a\": \"\\ud800\"}", "{\"a\": \"\\udc00x\"}",
            "{\"a\": \"tab\there\"}", "{\"a\": \"\\x41\"}", "", "   ", "{\"a\": tru}",
            "[".repeat(Json.MAX_DEPTH + 1) + "]".repeat(Json.MAX_DEPTH + 1)}) {
            assertThrows(Json.Malformed.class, () -> Json.parse(bad), bad);
        }
    }

    @Test
    void theWriterEscapesAndRoundTrips() throws Json.Malformed {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("id", "a\"b\\c\n\u0001\u007f");
        value.put("n", 7L);
        value.put("d", 0.25);
        value.put("none", null);
        value.put("list", List.of(1, "x", false));
        value.put("num", new Json.Num("-1.5E+3"));
        String text = Json.write(value);
        assertEquals("{\"id\":\"a\\\"b\\\\c\\n\\u0001\\u007f\",\"n\":7,\"d\":0.25,\"none\":null,"
            + "\"list\":[1,\"x\",false],\"num\":-1.5E+3}", text);
        Object back = Json.parse(text);
        assertEquals("a\"b\\c\n\u0001\u007f", ((Map<?, ?>) back).get("id"));
        assertThrows(IllegalArgumentException.class, () -> Json.write(Double.NaN));
        assertThrows(IllegalArgumentException.class, () -> Json.write(new Object()));
    }

    @Test
    void thePipeNameIsTheTokensHash() {
        // The same vectors are in tests/test_modclient.py: both ends derive one name.
        assertEquals("\\\\.\\pipe\\optilux-259f63a5ba1ef1eb91eb57b3aa0f4732", PipeName.of("T".repeat(43)));
        assertEquals("\\\\.\\pipe\\optilux-6fe187d6673374b0f58a87a64a213784",
            PipeName.of("AZaz09_-".repeat(5) + "abc"));
    }
}
