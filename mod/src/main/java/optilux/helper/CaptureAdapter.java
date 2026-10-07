package optilux.helper;

import com.mojang.blaze3d.platform.NativeImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.function.BiConsumer;
import java.util.function.BooleanSupplier;
import java.util.function.LongSupplier;
import net.minecraft.client.Screenshot;
import optilux.helper.core.Capture;
import optilux.helper.core.Errors;
import optilux.helper.core.FrameClock;
import optilux.helper.core.Protocol;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * `frames.capture` (docs/mod.md#8-capture). At the capture point the active capture takes the
 * frame through the vanilla screenshot readback F2 uses (Screenshot.takeScreenshot on the main
 * render target, alpha forced opaque), whose image arrives on the render thread frames later; a
 * writer pool writes it with NativeImage.writeToFile, F2's own PNG writer, and hashes the file. At
 * {@link #MAX_PENDING} pending frames the render thread waits for a writer (time, not
 * correctness), but only while a writer holds one: a readback in flight arrives through the render
 * thread itself, so readbacks alone may pass the cap (a few frames of fence latency in practice).
 * One capture at a time (the `capture` resource); every mutating command answers busy meanwhile. On a timeout, cancel, disconnect or world leave the capture stops,
 * pending frames are still written and the manifest is marked incomplete.
 */
final class CaptureAdapter {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    /** Pending readbacks at most (docs/mod.md#8-capture: about 530 MB at 4K). */
    static final int MAX_PENDING = 16;

    private final FrameClock clock;
    private final LongSupplier sinceReload;
    private final BooleanSupplier inWorld;
    private final ExecutorService writers;
    private final BiConsumer<String, Map<String, Object>> events;
    private volatile Capture active;

    CaptureAdapter(FrameClock clock, LongSupplier sinceReload, BooleanSupplier inWorld,
        ExecutorService writers, BiConsumer<String, Map<String, Object>> events) {
        this.clock = clock;
        this.sinceReload = sinceReload;
        this.inWorld = inWorld;
        this.writers = writers;
        this.events = events;
    }

    Map<String, Protocol.Handler> handlers() {
        return Map.of("frames.capture", this::framesCapture);
    }

    private Map<String, Object> framesCapture(Protocol.Request request) throws Exception {
        Map<String, Object> args = request.args();
        for (String later : new String[] {"align", "flush", "after"}) {
            Object value = args.get(later);
            if (value != null && !Boolean.FALSE.equals(value)) {
                throw new Errors.Refused(Errors.UNSUPPORTED, "frames.capture." + later
                    + " is not built in this mod (align M3, flush M5)");
            }
        }
        if (args.get("every") != null && args.get("intervalMs") != null) {
            throw new Errors.Refused(Errors.BAD_REQUEST,
                "frames.capture takes every or intervalMs, not both");
        }
        Path directory = Path.of((String) args.get("directory"));
        if (!directory.isAbsolute()) {
            throw new Errors.Refused(Errors.BAD_REQUEST, "frames.capture.directory " + directory
                + " is not absolute; fix: give the full path");
        }
        if (!inWorld.getAsBoolean()) {
            throw new Errors.Refused(Errors.NOT_READY, "not in a world; fix: world.wait first");
        }
        int count = Math.toIntExact((Long) args.get("count"));
        int every = args.get("every") == null ? 1 : Math.toIntExact((Long) args.get("every"));
        long intervalNs = args.get("intervalMs") == null ? 0
            : Math.round((Double) args.get("intervalMs") * 1e6);
        Capture capture = new Capture(Capture.attemptFolder(directory), count, every, intervalNs);
        Map<String, Object> answer = run(capture);
        events.accept("capture.done", Map.of("manifest", answer.get("manifest")));
        return answer;
    }

    /** Run one capture to its end; a stop (timeout, cancel, leave) interrupts the wait. */
    Map<String, Object> run(Capture capture) throws Exception {
        active = capture;
        LOG.info("optilux-helper: capture into {}", capture.folder());
        try {
            return Tasks.unwrap(capture.done());
        } catch (InterruptedException stopped) {
            capture.stop("interrupted: the request was answered first");
            throw stopped;
        } finally {
            if (active == capture) {
                active = null;
            }
            capture.stop("ended");
        }
    }

    /** The capture point (render thread): the active capture's next frame, if this is one. */
    void capturePoint() throws InterruptedException {
        Capture capture = active;
        if (capture == null) {
            return;
        }
        FrameClock.Stamp stamp = clock.last();
        if (!capture.wants(stamp.frameIndex(), stamp.qpcNs())) {
            return;
        }
        capture.awaitSlot(MAX_PENDING);
        Capture.Frame frame = capture.take(stamp, sinceReload.getAsLong());
        if (frame == null) {
            return; // stopped or complete meanwhile
        }
        try {
            Screenshot.takeScreenshot(Tasks.minecraft().gameRenderer.mainRenderTarget(),
                image -> arrived(capture, frame, image));
        } catch (RuntimeException error) {
            capture.dropped(frame, false, "readback failed: " + error);
        }
    }

    /** The frame's image arrived (render thread): a writer writes and hashes it. */
    private void arrived(Capture capture, Capture.Frame frame, NativeImage image) {
        capture.arrived(frame);
        try {
            writers.execute(() -> write(capture, frame, image));
        } catch (RuntimeException error) {
            image.close();
            capture.dropped(frame, true, "no writer took it: " + error);
        }
    }

    /**
     * Write and hash one frame. Its capture.frame event goes out before the frame counts as
     * written, so it precedes capture.done and the answer; a failed write leaves no file.
     */
    private void write(Capture capture, Capture.Frame frame, NativeImage image) {
        Path file = capture.folder().resolve(frame.name());
        String sha256;
        try (image) {
            sha256 = writeFrame(image, file);
        } catch (Throwable error) {
            LOG.warn("optilux-helper: capture frame {} not written", frame.name(), error);
            try {
                Files.deleteIfExists(file);
            } catch (IOException | RuntimeException left) {
                LOG.warn("optilux-helper: {} left behind: {}", file, left.toString());
            }
            capture.dropped(frame, true, "write failed: " + error);
            return;
        }
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("name", frame.name());
        data.put("sha256", sha256);
        data.put("frameIndex", frame.frameIndex());
        events.accept("capture.frame", data);
        capture.written(frame, sha256);
    }

    /** F2's PNG writer (NativeImage.writeToFile), then the written file's SHA-256. */
    static String writeFrame(NativeImage image, Path file) throws IOException {
        image.writeToFile(file);
        return Capture.sha256(file);
    }
}
