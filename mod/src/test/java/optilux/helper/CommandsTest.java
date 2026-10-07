package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import java.util.Set;
import optilux.helper.core.Commands;
import optilux.helper.core.Errors;
import optilux.helper.core.Json;
import org.junit.jupiter.api.Test;

/**
 * commands.json as the mod reads it: the error codes equal docs/mod-protocol.md#errors (Errors),
 * the 17 M1 commands, known argument keys and result types, the defaults filled by the check.
 * The harness's test checks the same file against the doc's table (tests/test_modclient.py).
 */
class CommandsTest {
    @Test
    void theTableAsBuilt() {
        Commands commands = Wire.COMMANDS;
        assertEquals(1, commands.protocol());
        assertEquals(Errors.ALL, commands.errors());
        assertEquals(List.of("window", "capture", "path", "timers"), commands.resources());
        List<String> m1 = commands.all().values().stream()
            .filter(c -> c.phase().equals("M1")).map(Commands.Command::name).toList();
        assertEquals(List.of("hello", "selftest", "state", "world.wait", "command", "ticks.step",
            "ready", "camera.place", "camera.get", "shaders.reload", "shaders.options",
            "frames.index", "frames.capture", "input.block", "hud.set", "cancel", "quit"), m1);
        Set<String> types = Set.of("string", "integer", "number", "boolean", "object", "array", "id");
        for (Commands.Command command : commands.all().values()) {
            assertTrue(Set.of("M1", "M2", "M3", "M5", "post").contains(command.phase()), command.name());
            for (String type : command.result().values()) {
                assertTrue(types.contains(type.replace("|null", "")), command.name() + ": " + type);
            }
            for (String key : command.result().keySet()) {
                assertTrue(!commands.common().containsKey(key), command.name() + " repeats " + key);
            }
        }
        assertEquals(Map.of("frameIndex", "integer", "sinceReload", "integer", "qpcNs", "integer"),
            commands.common());
    }

    @Test
    void theCheckFillsDefaultsAndTypesValues() throws Exception {
        Commands commands = Wire.COMMANDS;
        Map<String, Object> args = commands.check(commands.get("shaders.reload"),
            Json.parse("{\"timeoutSeconds\": 30}"));
        assertEquals(Map.of("framesAfter", 2L, "timeoutSeconds", 30.0), args);
        args = commands.check(commands.get("cancel"), Json.parse("{\"id\": \"a\"}"));
        assertEquals(Map.of("id", "a"), args);
        args = commands.check(commands.get("cancel"), Json.parse("{\"id\": 9007199254740993}"));
        assertEquals(Map.of("id", 9007199254740993L), args);
        Errors.Refused refused = assertThrows(Errors.Refused.class, () -> commands.check(
            commands.get("camera.path"), Json.parse("{\"kind\": \"spin\", \"params\": {}, \"clock\": \"frame\"}")));
        assertEquals(Errors.BAD_REQUEST, refused.code());
        assertEquals("camera.path.kind must be one of yawSweep, keyframes", refused.getMessage());
        refused = assertThrows(Errors.Refused.class, () -> commands.check(commands.get("cancel"),
            Json.parse("{\"id\": 99999999999999999999}")));
        assertEquals("cancel.id is outside the 64-bit range", refused.getMessage());
        assertThrows(Errors.Refused.class, () -> commands.check(commands.get("quit"), null));
    }

    @Test
    void anUnknownArgumentKeyOrTypeFailsTheLoad() {
        String base = "{\"protocol\": 1, \"common\": {}, \"errors\": " + Json.write(Errors.ALL)
            + ", \"resources\": [], \"commands\": [{\"name\": \"x\", \"phase\": \"M1\", "
            + "\"result\": {}, \"args\": {\"a\": %s}}]}";
        Commands.parse(String.format(base, "{\"type\": \"integer\", \"min\": 1}"));
        assertThrows(IllegalArgumentException.class,
            () -> Commands.parse(String.format(base, "{\"type\": \"integer\", \"minimum\": 1}")));
        assertThrows(IllegalArgumentException.class,
            () -> Commands.parse(String.format(base, "{\"type\": \"float\"}")));
    }
}
