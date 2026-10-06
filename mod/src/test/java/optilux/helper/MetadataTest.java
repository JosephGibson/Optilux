package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.file.Path;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipFile;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;

/**
 * The built jar's fabric.mod.json (docs/mod.md#5-safety): one client entrypoint, no access
 * widener, no nested jars, and `depends` equal to the platform file, derived here on its own from
 * config/platforms/&lt;id&gt;.json and the pinned jars, apart from the harness's generator.
 */
class MetadataTest {
    @Test
    void oneClientEntrypointNoAccessWidenerNoNestedJars() throws IOException {
        try (ZipFile jar = new ZipFile(Pinned.builtJar().toFile())) {
            JsonObject meta = Pinned.json(jar, "fabric.mod.json");
            assertEquals("optilux-helper", meta.get("id").getAsString());
            assertEquals("client", meta.get("environment").getAsString());
            JsonObject entrypoints = meta.getAsJsonObject("entrypoints");
            assertEquals(Set.of("client"), entrypoints.keySet());
            JsonArray client = entrypoints.getAsJsonArray("client");
            assertEquals(1, client.size());
            String entry = client.get(0).getAsString().replace('.', '/') + ".class";
            byte[] entryClass = Pinned.bytes(jar, entry);
            assertNotNull(entryClass, "the entrypoint class is not in the jar");
            String[] interfaces = new ClassReader(entryClass).getInterfaces();
            assertEquals(List.of("net/fabricmc/api/ClientModInitializer"), List.of(interfaces));

            assertFalse(meta.has("accessWidener"), "an access widener is declared");
            assertFalse(meta.has("jars"), "nested jars are declared");
            List<String> nested = Collections.list(jar.entries()).stream()
                .map(e -> e.getName())
                .filter(name -> name.startsWith("META-INF/jars/") || name.endsWith(".jar"))
                .toList();
            assertEquals(List.of(), nested);
            assertEquals(Set.of("schemaVersion", "id", "version", "name", "description",
                "license", "environment", "entrypoints", "mixins", "depends"), meta.keySet());

            JsonArray mixins = meta.getAsJsonArray("mixins");
            assertEquals(1, mixins.size());
            JsonObject config = Pinned.json(jar, mixins.get(0).getAsString());
            assertEquals("optilux.helper.MixinGate", config.get("plugin").getAsString());
            assertTrue(config.get("required").getAsBoolean());
        }
    }

    @Test
    void dependsEqualThePlatformFile() throws IOException {
        JsonObject inputs = Pinned.inputs();
        JsonObject platform = Pinned.json(Path.of(inputs.get("platformFile").getAsString()));
        Path store = Path.of(inputs.get("store").getAsString());
        Map<String, String> expected = new LinkedHashMap<>();
        expected.put("minecraft", "=" + platform.get("minecraft").getAsString());
        expected.put("fabricloader",
            "=" + platform.getAsJsonObject("loader").get("version").getAsString());
        JsonObject bench = platform.getAsJsonObject("tiers").getAsJsonObject("bench");
        for (JsonElement element : bench.getAsJsonArray("mods")) {
            JsonObject mod = element.getAsJsonObject();
            Path path = store.resolve(mod.get("file").getAsString());
            try (ZipFile pinned = Pinned.open(path, "sha512", mod.get("sha512").getAsString())) {
                JsonObject meta = Pinned.json(pinned, "fabric.mod.json");
                expected.put(meta.get("id").getAsString(), "=" + meta.get("version").getAsString());
            }
        }
        assertEquals(Set.of("minecraft", "fabricloader", "fabric-api", "sodium", "iris"),
            expected.keySet());

        Map<String, String> declared = new LinkedHashMap<>();
        try (ZipFile jar = new ZipFile(Pinned.builtJar().toFile())) {
            JsonObject depends = Pinned.json(jar, "fabric.mod.json").getAsJsonObject("depends");
            for (String key : depends.keySet()) {
                declared.put(key, depends.get(key).getAsString());
            }
        }
        assertEquals(expected, declared);
    }
}
