package optilux.helper;

import com.mojang.blaze3d.platform.NativeImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BiConsumer;
import java.util.function.BooleanSupplier;
import java.util.function.LongSupplier;
import java.util.function.Supplier;
import net.minecraft.client.Screenshot;
import optilux.helper.core.Capture;
import optilux.helper.core.Errors;
import optilux.helper.core.FrameClock;
import optilux.helper.core.Protocol;
import optilux.helper.core.Readiness;
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
 * With `ready` its frame poll judges the readiness predicate on the renderer's reading at each
 * frame head until it holds, inside the mod (docs/mod.md#6-time-and-determinism); with `align`
 * only frames at the phase are taken, judged at the capture point on Iris's counter, the value the
 * frame's shaders read (Iris advances it at GameRenderer.render HEAD); with `images` false a frame
 * is its stamps, with no readback or file.
 * One capture at a time (the `capture` resource); every mutating command answers busy meanwhile.
 * On a timeout, cancel, disconnect or world leave the capture stops, pending frames are still
 * written and the manifest is marked incomplete; the resource is freed after them (a world leave
 * frees every resource at once).
 */
final class CaptureAdapter {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    /** Pending readbacks at most (docs/mod.md#8-capture: about 530 MB at 4K). */
    static final int MAX_PENDING = 16;
    /** A stopped capture's wait for its pending frames: 16 4K PNGs on 4 writers take seconds. */
    static final Duration DRAIN = Duration.ofSeconds(30);

    private final FrameClock clock;
    private final LongSupplier sinceReload;
    private final BooleanSupplier inWorld;
    private final Supplier<Readiness.Reading> readings;
    private final LongSupplier nanos;
    private final ExecutorService writers;
    private final BiConsumer<String, Map<String, Object>> events;
    /** The capture the capture point serves, and whether its request is still unanswered. */
    private record Active(Capture capture, BooleanSupplier live) {
    }

    // A world leave frees the resource at once, so an ending capture clears only its own slot.
    private final AtomicReference<Active> active = new AtomicReference<>();

    /** `readings`: the renderer's reading (render thread); `nanos`: the readiness clock. */
    CaptureAdapter(FrameClock clock, LongSupplier sinceReload, BooleanSupplier inWorld,
        Supplier<Readiness.Reading> readings, LongSupplier nanos, ExecutorService writers,
        BiConsumer<String, Map<String, Object>> events) {
        this.clock = clock;
        this.sinceReload = sinceReload;
        this.inWorld = inWorld;
        this.readings = readings;
        this.nanos = nanos;
        this.writers = writers;
        this.events = events;
    }

    Map<String, Protocol.Handler> handlers() {
        return Map.of("frames.capture", this::framesCapture);
    }

    private Map<String, Object> framesCapture(Protocol.Request request) throws Exception {
        Map<String, Object> args = request.args();
        for (String later : new String[] {"flush", "after"}) {
            Object value = args.get(later);
            if (value != null && !Boolean.FALSE.equals(value)) {
                throw new Errors.Refused(Errors.UNSUPPORTED, "frames.capture." + later
                    + " is not built in this mod (M5)");
            }
        }
        if (args.get("every") != null && args.get("intervalMs") != null) {
            throw new Errors.Refused(Errors.BAD_REQUEST,
                "frames.capture takes every or intervalMs, not both");
        }
        Capture.Align align = args.get("align") == null ? null : Capture.Align.of(args.get("align"));
        Readiness ready = args.get("ready") == null ? null
            : Capture.readiness(args.get("ready"), nanos.getAsLong());
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
        Capture capture = new Capture(Capture.attemptFolder(directory), count, every, intervalNs,
            align, ready, !Boolean.FALSE.equals(args.get("images")));
        Map<String, Object> answer = run(capture, request::live);
        events.accept("capture.done", Map.of("manifest", answer.get("manifest")));
        return answer;
    }

    /**
     * Run one capture to its end; a stop (timeout, cancel, leave) interrupts the wait, and the
     * stopped capture's pending frames are written or dropped before this returns (at most
     * DRAIN), so its resource is freed with them. Once `live` turns false (the request was
     * answered first) the render thread neither judges its gate nor takes a frame, though the
     * interrupt that stops it comes after the answer (Protocol.stop).
     */
    Map<String, Object> run(Capture capture, BooleanSupplier live) throws Exception {
        Active mine = new Active(capture, live);
        active.set(mine);
        LOG.info("optilux-helper: capture into {}", capture.folder());
        try {
            return Tasks.unwrap(capture.done());
        } catch (InterruptedException stopped) {
            capture.stop("interrupted: the request was answered first");
            drain(capture);
            throw stopped;
        } finally {
            active.compareAndSet(mine, null);
            capture.stop("ended");
        }
    }

    /**
     * Wait for a stopped capture's manifest, which follows its pending frames: at most DRAIN, an
     * interrupt ignored (the request's own already ended the wait it was meant for). Readbacks
     * arrive through the render thread, so a game that stops rendering ends the wait at DRAIN.
     */
    static void drain(Capture capture) {
        long until = System.nanoTime() + DRAIN.toNanos();
        boolean interrupted = false;
        try {
            while (true) {
                long left = until - System.nanoTime();
                if (left <= 0) {
                    LOG.warn("optilux-helper: capture {} still had {} frames pending after {} s",
                        capture.folder(), capture.pending(), DRAIN.toSeconds());
                    return;
                }
                try {
                    capture.done().get(left, TimeUnit.NANOSECONDS);
                    return;
                } catch (InterruptedException again) {
                    interrupted = true;
                } catch (TimeoutException late) {
                    // the next turn logs it
                } catch (ExecutionException failed) {
                    LOG.warn("optilux-helper: stopped capture {}: {}", capture.folder(),
                        failed.getCause().toString());
                    return;
                }
            }
        } finally {
            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    /** At every frame head (render thread): the active capture's ready gate, while closed. */
    void frame() {
        Active current = active.get();
        if (current == null || !current.live().getAsBoolean() || !current.capture().awaitingReady()) {
            return;
        }
        Capture capture = current.capture();
        Map<String, Object> report = capture.ready(readings.get(), nanos.getAsLong(),
            clock.last().frameIndex());
        if (report != null) {
            LOG.info("optilux-helper: capture into {} ready: {}", capture.folder(), report);
        }
    }

    /** The capture point (render thread): the active capture's next frame, if this is one. */
    void capturePoint() throws InterruptedException {
        Active current = active.get();
        if (current == null || !current.live().getAsBoolean()) {
            return;
        }
        Capture capture = current.capture();
        FrameClock.Stamp stamp = clock.last();
        long counter = sinceReload.getAsLong();
        if (!capture.wants(stamp.frameIndex(), stamp.qpcNs(), counter)) {
            return;
        }
        if (!capture.images()) {
            capture.take(stamp, counter);
            return;
        }
        capture.awaitSlot(MAX_PENDING);
        Capture.Frame frame = capture.take(stamp, counter);
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
