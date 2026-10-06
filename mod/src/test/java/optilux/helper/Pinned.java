package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * What the tests read: build/optilux/inputs.json (written by `optilux mod build|test`, path in
 * -Doptilux.inputs), the built jar (-Doptilux.jar) and pinned jars checked by their digests first.
 */
final class Pinned {
    private Pinned() {
    }

    static JsonObject inputs() {
        return json(Path.of(property("optilux.inputs")));
    }

    static Path builtJar() {
        return Path.of(property("optilux.jar"));
    }

    static String property(String name) {
        String value = System.getProperty(name);
        assertNotNull(value, "-D" + name + " is unset; run the tests through `optilux mod test`");
        return value;
    }

    static JsonObject json(Path path) {
        try {
            return JsonParser.parseString(Files.readString(path)).getAsJsonObject();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    static JsonObject json(ZipFile jar, String entry) {
        return JsonParser.parseString(new String(bytes(jar, entry), StandardCharsets.UTF_8))
            .getAsJsonObject();
    }

    /** An entry's bytes, or null when the jar lacks it. */
    static byte[] bytes(ZipFile jar, String entry) {
        ZipEntry found = jar.getEntry(entry);
        if (found == null) {
            return null;
        }
        try (InputStream stream = jar.getInputStream(found)) {
            return stream.readAllBytes();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    /** Open a jar after checking its digest; algorithm is sha1 or sha512. */
    static ZipFile open(Path path, String algorithm, String pin) {
        assertEquals(pin, digest(path, algorithm), path + ": " + algorithm + " differs from its pin");
        try {
            return new ZipFile(path.toFile());
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    static String digest(Path path, String algorithm) {
        try (InputStream stream = Files.newInputStream(path)) {
            MessageDigest digest = MessageDigest.getInstance(algorithm.equals("sha1") ? "SHA-1" : "SHA-512");
            byte[] buffer = new byte[1 << 20];
            int read;
            while ((read = stream.read(buffer)) > 0) {
                digest.update(buffer, 0, read);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
