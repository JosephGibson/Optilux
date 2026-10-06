package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import optilux.helper.core.Commands;
import optilux.helper.core.Errors;
import optilux.helper.core.Json;

/** What the protocol tests share: the real commands.json and the check of an answer against it. */
final class Wire {
    static final Commands COMMANDS = Commands.parse(resource("commands.json"));

    private Wire() {
    }

    static String resource(String name) {
        try (InputStream stream = Wire.class.getClassLoader().getResourceAsStream(name)) {
            assertNotNull(stream, name + " is not on the test classpath");
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> parse(String line) {
        try {
            return (Map<String, Object>) Json.parse(line);
        } catch (Json.Malformed error) {
            throw new AssertionError("the mod wrote no JSON: " + line, error);
        }
    }

    /**
     * An answer as the envelope and commands.json say: ok with a result holding exactly the
     * command's fields and the common ones, each of its type; or an error with a known code.
     */
    @SuppressWarnings("unchecked")
    static void check(String command, Map<String, Object> answer) {
        assertTrue(answer.containsKey("id"), "no id in " + answer);
        if (Boolean.FALSE.equals(answer.get("ok"))) {
            assertEquals(Set.of("id", "ok", "error"), answer.keySet());
            Map<String, Object> error = (Map<String, Object>) answer.get("error");
            assertEquals(Set.of("code", "message"), error.keySet());
            assertTrue(Errors.ALL.contains(error.get("code")), "unknown code in " + answer);
            assertTrue(error.get("message") instanceof String text && !text.isEmpty());
            return;
        }
        assertEquals(Set.of("id", "ok", "result"), answer.keySet(), "envelope of " + answer);
        assertEquals(true, answer.get("ok"));
        Map<String, Object> result = (Map<String, Object>) answer.get("result");
        Commands.Command spec = COMMANDS.get(command);
        assertNotNull(spec, "no command " + command + " in commands.json");
        Set<String> expected = new LinkedHashSet<>(spec.result().keySet());
        expected.addAll(COMMANDS.common().keySet());
        assertEquals(expected, result.keySet(), command + " result fields");
        for (Map.Entry<String, Object> field : result.entrySet()) {
            String type = spec.result().containsKey(field.getKey())
                ? spec.result().get(field.getKey()) : COMMANDS.common().get(field.getKey());
            assertTrue(matches(type, field.getValue()), command + "." + field.getKey() + " = "
                + field.getValue() + " is not " + type);
        }
    }

    static boolean matches(String type, Object value) {
        if (value == null) {
            return type.endsWith("|null");
        }
        return switch (type.replace("|null", "")) {
            case "string" -> value instanceof String;
            case "integer" -> value instanceof Json.Num num && num.isInteger();
            case "number" -> value instanceof Json.Num;
            case "boolean" -> value instanceof Boolean;
            case "object" -> value instanceof Map<?, ?>;
            case "array" -> value instanceof List<?>;
            case "id" -> value instanceof String || value instanceof Json.Num num && num.isInteger();
            default -> throw new AssertionError("unknown result type " + type);
        };
    }
}
