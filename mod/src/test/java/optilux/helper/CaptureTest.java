package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
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
import optilux.helper.core.Errors;
import optilux.helper.core.FrameClock;
import optilux.helper.core.Json;
import optilux.helper.core.Readiness;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * frames.capture's files and manifest (docs/mod.md#8-capture): a frame written by the capture
 * adapter's own writer (F2's NativeImage.writeToFile) decodes, with an independent PNG decoder, to
 * the pixels the readback put in the image, and the manifest's sha256 equals the file's; the frame
 * plan, the pending cap that never waits on a readback alone, the stop that marks the manifest
 * incomplete, and a new folder per attempt; align on a fake clock (the phase, the wrap, the cycles
 * refused), ready on a fake predicate (the first frame after it, minSeconds) and frames without
 * images.
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
        assertTrue(capture.wants(40, stamp(40).qpcNs(), 12L));
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
        assertTrue(every.wants(10, 0, 0L));
        every.take(stamp(10), 0L);
        assertFalse(every.wants(11, 0, 0L));
        assertTrue(every.wants(12, 0, 0L));
        every.take(stamp(12), 0L);
        assertTrue(every.wants(14, 0, 0L));
        assertEquals("frame-00003.png", every.take(stamp(14), 0L).name());
        assertFalse(every.wants(16, 0, 0L), "the count is reached");

        Capture timed = new Capture(Capture.attemptFolder(temp), 3, 1, 50_000_000L);
        assertTrue(timed.wants(1, 1_000_000_000L, 0L));
        timed.take(new FrameClock.Stamp(1, 1_000_000_000L, 0), 0L);
        assertFalse(timed.wants(2, 1_040_000_000L, 0L));
        assertTrue(timed.wants(3, 1_050_000_000L, 0L));
        // A long frame: the next is due an interval after the frame taken, so no catch-up burst.
        timed.take(new FrameClock.Stamp(3, 1_200_000_000L, 0), 0L);
        assertFalse(timed.wants(4, 1_210_000_000L, 0L));
        assertTrue(timed.wants(5, 1_250_000_000L, 0L));
    }

    @Test
    void aStopBetweenWantsAndTakeTakesNothing() throws Exception {
        Capture capture = new Capture(Capture.attemptFolder(temp), 2, 1, 0);
        assertTrue(capture.wants(8, 0, 0L));
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
        assertFalse(capture.wants(4, 0, 0L));
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

    private static Object json(String text) {
        try {
            return Json.parse(text);
        } catch (Json.Malformed error) {
            throw new AssertionError(error);
        }
    }

    /** A reading where the predicate holds, or fails on the build queue (Sodium's check alike). */
    private static Readiness.Reading reading(boolean holds) {
        return new Readiness.Reading(true, true, 100, holds ? 0 : 3, 0, 0, 0, 0, 0, true, holds);
    }

    /** One frame on the render thread: the head's ready gate, then the capture point. */
    private static void frame(Capture capture, long frameIndex, long nowNanos, long counter,
        boolean holds) {
        capture.ready(reading(holds), nowNanos, frameIndex);
        FrameClock.Stamp stamp = new FrameClock.Stamp(frameIndex, nowNanos, nowNanos - 900_000L);
        if (capture.wants(frameIndex, nowNanos, counter)) {
            assertNotNull(capture.take(stamp, counter));
        }
    }

    @SuppressWarnings("unchecked")
    private static List<String> column(Map<String, Object> answer, String key) {
        return ((List<Map<String, Object>>) answer.get("frames")).stream()
            .map(f -> String.valueOf(f.get(key))).toList();
    }

    @Test
    void anAlignedCaptureTakesFramesAtItsPhaseAcrossTheWrap() throws Exception {
        // Iris's counter wraps at 720720, which 16 divides: phase 3 recurs every 16 frames
        // through the wrap. Frame k shows counter 720699 + k, 0 again at frame 21.
        Capture capture = new Capture(Capture.attemptFolder(temp), 3, 1, 0,
            new Capture.Align(16, 3), null, false);
        long counter = 720_700;
        for (long frameIndex = 1; frameIndex <= 60; frameIndex++) {
            frame(capture, frameIndex, frameIndex * 7_000_000L, counter, true);
            counter = (counter + 1) % Capture.WRAP;
        }
        Map<String, Object> answer = capture.done().get(5, TimeUnit.SECONDS);
        assertEquals(List.of("720707", "3", "19"), column(answer, "sinceReload"));
        assertEquals(List.of("8", "24", "40"), column(answer, "frameIndex"), "16 frames apart");
        Capture unknown = new Capture(Capture.attemptFolder(temp), 1, 1, 0,
            new Capture.Align(1, 0), null, false);
        assertFalse(unknown.wants(1, 0, null), "an aligned frame needs Iris's counter");
    }

    @Test
    void anAlignNeedsACycleDividingTheWrapAndAPhaseBelowIt() throws Exception {
        assertEquals(new Capture.Align(16, 3), Capture.Align.of(json("{\"cycle\":16,\"phase\":3}")));
        assertEquals(new Capture.Align(720720, 0),
            Capture.Align.of(json("{\"cycle\":720720,\"phase\":0}")));
        Errors.Refused refused = assertThrows(Errors.Refused.class,
            () -> Capture.Align.of(json("{\"cycle\":32,\"phase\":0}")));
        assertEquals(Errors.BAD_REQUEST, refused.code());
        assertTrue(refused.getMessage().contains("32 does not divide 720720"), refused.getMessage());
        for (String bad : List.of("{\"cycle\":17,\"phase\":0}", "{\"cycle\":4,\"phase\":4}",
            "{\"cycle\":0,\"phase\":0}", "{\"cycle\":4,\"phase\":-1}", "{\"cycle\":4}",
            "{\"cycle\":4,\"phase\":1,\"flush\":true}", "{\"cycle\":4.5,\"phase\":1}",
            "{\"cycle\":1441440,\"phase\":0}", "[4,1]")) {
            assertEquals(Errors.BAD_REQUEST, assertThrows(Errors.Refused.class,
                () -> Capture.Align.of(json(bad)), bad).code(), bad);
        }
        assertThrows(IllegalArgumentException.class, () -> new Capture.Align(32, 0));
    }

    @Test
    @SuppressWarnings("unchecked")
    void aReadyCaptureTakesTheFirstFrameAfterThePredicate() throws Exception {
        // The predicate holds from frame 5's head; over 3 stable frames the wait is over at frame
        // 7's head, so frame 7, the first rendered after it held, is the first taken.
        Capture capture = new Capture(Capture.attemptFolder(temp), 2, 1, 0, null,
            new Readiness(3, 0, 0), false);
        for (long frameIndex = 1; frameIndex <= 6; frameIndex++) {
            frame(capture, frameIndex, frameIndex * 7_000_000L, frameIndex, frameIndex >= 5);
            assertTrue(capture.awaitingReady(), "open at frame " + frameIndex);
        }
        for (long frameIndex = 7; frameIndex <= 12; frameIndex++) {
            frame(capture, frameIndex, frameIndex * 7_000_000L, frameIndex, true);
        }
        Map<String, Object> answer = capture.done().get(5, TimeUnit.SECONDS);
        assertEquals(List.of("7", "8"), column(answer, "frameIndex"));
        Map<String, Object> ready = (Map<String, Object>) answer.get("ready");
        assertEquals(7L, ready.get("frameIndex"));
        assertEquals("buildQueue", ready.get("limitedBy"));
        assertEquals(7, ready.get("frames"));
        Map<String, Object> manifest = (Map<String, Object>) Json.parse(
            Files.readString(Path.of((String) answer.get("manifest"))));
        assertEquals("7", ((Map<String, Object>) manifest.get("ready")).get("frameIndex").toString());
    }

    @Test
    @SuppressWarnings("unchecked")
    void aReadyCaptureWaitsMinSecondsFromTheRequest() throws Exception {
        // The request at 1 s with minSeconds 0.5; the predicate holds from the first head and
        // frames come 100 ms apart, so the wait ends at frame 5's head, 1.5 s.
        long request = 1_000_000_000L;
        Capture capture = new Capture(Capture.attemptFolder(temp), 1, 1, 0, null,
            Capture.readiness(json("{\"stableFrames\":1,\"minSeconds\":0.5}"), request), false);
        for (long frameIndex = 1; frameIndex <= 10; frameIndex++) {
            frame(capture, frameIndex, request + frameIndex * 100_000_000L, frameIndex, true);
        }
        Map<String, Object> answer = capture.done().get(5, TimeUnit.SECONDS);
        assertEquals(List.of("5"), column(answer, "frameIndex"));
        Map<String, Object> ready = (Map<String, Object>) answer.get("ready");
        assertEquals("minSeconds", ready.get("limitedBy"));
        assertEquals(0.5, (Double) ready.get("seconds"), 1e-9);
        assertEquals(0.1, (Double) ready.get("predicateSeconds"), 1e-9);
    }

    @Test
    @SuppressWarnings("unchecked")
    void anAlignedReadyCaptureTakesTheFirstFrameAtThePhaseThenEveryN() throws Exception {
        // selftest's combination with every 8: the predicate holds from frame 10, two stable
        // frames open the gate at frame 11, the first frame at phase 1 of 4 from it is 13, then
        // every 8 frames, each at the phase (the counter is the frame index here).
        Capture capture = new Capture(Capture.attemptFolder(temp), 3, 8, 0,
            new Capture.Align(4, 1), Capture.readiness(
                json("{\"stableFrames\":2,\"minSeconds\":0}"), 0), false);
        for (long frameIndex = 1; frameIndex <= 40; frameIndex++) {
            frame(capture, frameIndex, frameIndex * 7_000_000L, frameIndex, frameIndex >= 10);
        }
        Map<String, Object> answer = capture.done().get(5, TimeUnit.SECONDS);
        assertEquals(List.of("13", "21", "29"), column(answer, "frameIndex"));
        assertEquals(11L, ((Map<String, Object>) answer.get("ready")).get("frameIndex"));
        Capture timed = new Capture(Capture.attemptFolder(temp), 2, 1, 50_000_000L,
            new Capture.Align(4, 1), null, false);
        for (long frameIndex = 1; frameIndex <= 40; frameIndex++) {
            frame(timed, frameIndex, frameIndex * 7_000_000L, frameIndex, true);
        }
        // 50 ms apart at 7 ms a frame: frame 1, then the first at the phase from 57 ms on.
        assertEquals(List.of("1", "9"), column(timed.done().get(5, TimeUnit.SECONDS), "frameIndex"));
    }

    @Test
    void aReadyArgumentIsTheReadyCommandsArguments() throws Exception {
        assertNotNull(Capture.readiness(json("{\"stableFrames\":10,\"minSeconds\":1.5}"), 0));
        for (String bad : List.of("{\"stableFrames\":0,\"minSeconds\":0}",
            "{\"stableFrames\":10}", "{\"stableFrames\":10,\"minSeconds\":-1}",
            "{\"stableFrames\":10,\"minSeconds\":3601}", "{\"stableFrames\":2.5,\"minSeconds\":0}",
            "{\"stableFrames\":10,\"minSeconds\":0,\"timeoutSeconds\":5}", "true")) {
            assertEquals(Errors.BAD_REQUEST, assertThrows(Errors.Refused.class,
                () -> Capture.readiness(json(bad), 0), bad).code(), bad);
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    void aCaptureWithoutImagesIsItsStampsAndWritesNoFrame() throws Exception {
        Capture capture = new Capture(Capture.attemptFolder(temp), 2, 1, 0, null, null, false);
        assertTrue(capture.wants(40, stamp(40).qpcNs(), 12L));
        assertNull(capture.take(stamp(40), 12L).name(), "no file");
        assertEquals(0, capture.pending(), "no readback in flight");
        assertFalse(capture.done().isDone());
        assertFalse(capture.wants(40, stamp(40).qpcNs(), 12L));
        capture.take(stamp(41), 13L);
        Map<String, Object> answer = capture.done().get(5, TimeUnit.SECONDS);
        List<Map<String, Object>> frames = (List<Map<String, Object>>) answer.get("frames");
        assertEquals(List.of("frameIndex", "sinceReload", "qpcNs", "swapQpcNs"),
            List.copyOf(frames.get(0).keySet()));
        assertEquals(List.of("40", "41"), column(answer, "frameIndex"));
        assertTrue(answer.containsKey("ready") && answer.get("ready") == null, "ready: null");
        Map<String, Object> manifest = (Map<String, Object>) Json.parse(
            Files.readString(capture.folder().resolve(Capture.MANIFEST)));
        assertEquals(false, manifest.get("images"));
        assertEquals(true, manifest.get("complete"));
        assertEquals(frames.size(), ((List<?>) manifest.get("frames")).size());
        try (var files = Files.list(capture.folder())) {
            assertEquals(List.of(Capture.MANIFEST), files.map(f -> f.getFileName().toString()).toList());
        }
    }
}
