package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.mojang.blaze3d.platform.NativeImage;
import java.awt.image.BufferedImage;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import javax.imageio.ImageIO;
import optilux.helper.core.Capture;
import optilux.helper.core.FrameClock;
import optilux.helper.core.Json;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * frames.capture's files and manifest (docs/mod.md#8-capture): a frame written by the capture
 * adapter's own writer (F2's NativeImage.writeToFile) decodes, with an independent PNG decoder, to
 * the pixels the readback put in the image, and the manifest's sha256 equals the file's; the frame
 * plan, the pending cap that never waits on a readback alone, the stop that marks the manifest
 * incomplete, and a new folder per attempt.
 */
class CaptureTest {
    @TempDir
    Path temp;

    private static FrameClock.Stamp stamp(long frameIndex) {
        return new FrameClock.Stamp(frameIndex, frameIndex * 7_000_000L, frameIndex * 7_000_000L - 900_000L);
    }

    @Test
    @SuppressWarnings("unchecked")
    void theManifestHashesEachFileAndTheFileDecodesToTheCapturedBuffer() throws Exception {
        int width = 7;
        int height = 5;
        int[] captured = new int[width * height];
        Capture capture = new Capture(Capture.attemptFolder(temp), 1, 1, 0);
        assertTrue(capture.wants(40, stamp(40).qpcNs()));
        Capture.Frame frame = capture.take(stamp(40), 12L);
        // The readback's image: ABGR words with alpha forced opaque, as Screenshot.takeScreenshot
        // fills it from the mapped buffer.
        NativeImage image = new NativeImage(width, height, false);
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int abgr = 0xFF000000 | (x * 31 + y * 11 & 0xFF) << 16 | (255 - x * 9) << 8 | (y * 50 + x);
                captured[y * width + x] = abgr;
                image.setPixelABGR(x, y, abgr);
            }
        }
        capture.arrived(frame);
        String sha256;
        try (image) {
            sha256 = CaptureAdapter.writeFrame(image, capture.folder().resolve(frame.name()));
        }
        capture.written(frame, sha256);
        Map<String, Object> answer = capture.done().get(5, TimeUnit.SECONDS);

        Path manifestPath = Path.of((String) answer.get("manifest"));
        assertEquals(capture.folder().resolve(Capture.MANIFEST), manifestPath);
        Map<String, Object> manifest = (Map<String, Object>) Json.parse(Files.readString(manifestPath));
        assertEquals(true, manifest.get("complete"));
        // `every` is a frame count: an integer in the JSON, as the protocol fake writes it.
        assertTrue(Files.readString(manifestPath).contains("\"every\":1,"), "every is no integer");
        List<Map<String, Object>> frames = (List<Map<String, Object>>) manifest.get("frames");
        assertEquals(1, frames.size());
        Map<String, Object> entry = frames.get(0);
        assertEquals("frame-00001.png", entry.get("name"));
        Path file = capture.folder().resolve("frame-00001.png");
        assertEquals(Capture.sha256(file), entry.get("sha256"));
        assertEquals("40", entry.get("frameIndex").toString());
        assertEquals("12", entry.get("sinceReload").toString());
        assertEquals("280000000", entry.get("qpcNs").toString());
        assertEquals("279100000", entry.get("swapQpcNs").toString());
        assertEquals(List.of(), manifest.get("dropped"));
        assertEquals(sha256, ((List<Map<String, Object>>) answer.get("frames")).get(0).get("sha256"));

        BufferedImage decoded = ImageIO.read(file.toFile());
        assertNotNull(decoded, "the PNG does not decode");
        assertEquals(width, decoded.getWidth());
        assertEquals(height, decoded.getHeight());
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int argb = decoded.getRGB(x, y);
                int abgr = argb & 0xFF00FF00 | (argb & 0xFF) << 16 | (argb >> 16) & 0xFF;
                assertEquals(captured[y * width + x], abgr, "pixel " + x + "," + y);
            }
        }
    }

    @Test
    void framesAreTakenEveryNFramesOrEveryInterval() throws Exception {
        Capture every = new Capture(Capture.attemptFolder(temp), 3, 2, 0);
        assertTrue(every.wants(10, 0));
        every.take(stamp(10), 0L);
        assertFalse(every.wants(11, 0));
        assertTrue(every.wants(12, 0));
        every.take(stamp(12), 0L);
        assertTrue(every.wants(14, 0));
        assertEquals("frame-00003.png", every.take(stamp(14), 0L).name());
        assertFalse(every.wants(16, 0), "the count is reached");

        Capture timed = new Capture(Capture.attemptFolder(temp), 3, 1, 50_000_000L);
        assertTrue(timed.wants(1, 1_000_000_000L));
        timed.take(new FrameClock.Stamp(1, 1_000_000_000L, 0), 0L);
        assertFalse(timed.wants(2, 1_040_000_000L));
        assertTrue(timed.wants(3, 1_050_000_000L));
        // A long frame: the next is due an interval after the frame taken, so no catch-up burst.
        timed.take(new FrameClock.Stamp(3, 1_200_000_000L, 0), 0L);
        assertFalse(timed.wants(4, 1_210_000_000L));
        assertTrue(timed.wants(5, 1_250_000_000L));
    }

    @Test
    void aStopBetweenWantsAndTakeTakesNothing() throws Exception {
        Capture capture = new Capture(Capture.attemptFolder(temp), 2, 1, 0);
        assertTrue(capture.wants(8, 0));
        capture.stop("timeout");
        assertTrue(capture.done().isDone(), "nothing pending: the manifest is written at the stop");
        assertEquals(null, capture.take(stamp(8), 0L));
        assertEquals(0, capture.pending());
        try (var files = Files.list(capture.folder())) {
            assertEquals(List.of(Capture.MANIFEST), files.map(f -> f.getFileName().toString()).toList());
        }
    }

    @Test
    void thePendingCapWaitsOnlyForAWriter() throws Exception {
        Capture capture = new Capture(Capture.attemptFolder(temp), 10, 1, 0);
        Capture.Frame first = capture.take(stamp(1), 0L);
        Capture.Frame second = capture.take(stamp(2), 0L);
        // Two readbacks in flight, none with a writer: waiting would never end (the render thread
        // delivers readbacks), so the cap of 2 does not wait.
        capture.awaitSlot(2);
        capture.arrived(first);
        CountDownLatch waited = new CountDownLatch(1);
        Thread render = new Thread(() -> {
            try {
                capture.awaitSlot(2); // one in flight, one writing: the writer frees a slot
                waited.countDown();
            } catch (InterruptedException ignored) {
                // the test failed elsewhere
            }
        });
        render.start();
        assertFalse(waited.await(200, TimeUnit.MILLISECONDS), "the cap let a third frame through");
        capture.written(first, "00");
        assertTrue(waited.await(5, TimeUnit.SECONDS), "a written frame did not free the slot");
        assertEquals(1, capture.pending());
        capture.dropped(second, false, "readback failed: test");
        assertEquals(0, capture.pending());
    }

    @Test
    @SuppressWarnings("unchecked")
    void aStopEndsTheCaptureAfterThePendingFramesMarkedIncomplete() throws Exception {
        Capture capture = new Capture(Capture.attemptFolder(temp), 5, 1, 0);
        Capture.Frame frame = capture.take(stamp(3), 1L);
        capture.stop("cancelled");
        assertFalse(capture.wants(4, 0));
        assertFalse(capture.done().isDone(), "the manifest came before the pending frame");
        capture.arrived(frame);
        Files.writeString(capture.folder().resolve(frame.name()), "png");
        capture.written(frame, Capture.sha256(capture.folder().resolve(frame.name())));
        Map<String, Object> answer = capture.done().get(5, TimeUnit.SECONDS);
        Map<String, Object> manifest = (Map<String, Object>) Json.parse(
            Files.readString(Path.of((String) answer.get("manifest"))));
        assertEquals(false, manifest.get("complete"));
        assertEquals("cancelled", manifest.get("stopped"));
        assertEquals(1, ((List<?>) manifest.get("frames")).size());
    }

    @Test
    void eachAttemptGetsANewFolder() throws Exception {
        Path first = Capture.attemptFolder(temp.resolve("captures"));
        Path second = Capture.attemptFolder(temp.resolve("captures"));
        assertEquals("attempt-001", first.getFileName().toString());
        assertEquals("attempt-002", second.getFileName().toString());
        assertTrue(Files.isDirectory(second));
    }
}
