package optilux.helper.core;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * One `frames.capture` (docs/mod.md#8-capture): which frames to take, the frames in flight, and
 * the manifest. The capture point asks {@link #wants} once per frame on the render thread, then
 * {@link #take}s the frame; its readback arrives frames later ({@link #arrived}) and a writer
 * thread writes the PNG ({@link #written} or {@link #dropped}). When every taken frame is resolved
 * and the count is reached, or after {@link #stop}, capture.json is written beside the frames and
 * {@link #done} completes with the answer's fields: frames (name, sha256, frameIndex, sinceReload,
 * qpcNs, swapQpcNs), dropped and the manifest's path. Each attempt writes to a new subfolder of the
 * requested directory ({@link #attemptFolder}), so a retry never meets an earlier attempt's files.
 */
public final class Capture {
    public static final String MANIFEST = "capture.json";
    static final String ATTEMPT = "attempt-";

    /** A taken frame: its file name and the stamp of the frame it shows. */
    public record Frame(int ordinal, String name, long frameIndex, Long sinceReload, long qpcNs,
        long swapQpcNs) {
    }

    private final Path folder;
    private final int count;
    private final int every;
    private final long intervalNs;
    private final List<Map<String, Object>> frames = new ArrayList<>();
    private final List<Map<String, Object>> dropped = new ArrayList<>();
    private final CompletableFuture<Map<String, Object>> done = new CompletableFuture<>();
    private int taken;
    private long nextFrame = -1;
    private long nextQpcNs = -1;
    private int inFlight;
    private int writing;
    private String stopped;

    /** `every` frames apart, or `intervalNs` apart when it is positive. */
    public Capture(Path folder, int count, int every, long intervalNs) {
        if (count < 1 || every < 1) {
            throw new IllegalArgumentException("count " + count + " and every " + every + " must be positive");
        }
        this.folder = folder;
        this.count = count;
        this.every = every;
        this.intervalNs = intervalNs;
    }

    public Path folder() {
        return folder;
    }

    /** Whether the frame with this stamp is one to take (render thread). */
    public synchronized boolean wants(long frameIndex, long qpcNs) {
        if (stopped != null || taken >= count) {
            return false;
        }
        if (intervalNs > 0) {
            return nextQpcNs < 0 || qpcNs >= nextQpcNs;
        }
        return nextFrame < 0 || frameIndex >= nextFrame;
    }

    /**
     * Take the frame with this stamp: its file name and stamp, counted in flight; null when the
     * capture stopped or reached its count since {@link #wants} (a stop may land in between, and
     * after it the manifest may already be written). The next frame is due `every` frames or
     * `intervalNs` after this one, so a long frame never makes a burst of catch-up frames.
     */
    public synchronized Frame take(FrameClock.Stamp stamp, Long sinceReload) {
        if (stopped != null || taken >= count || done.isDone()) {
            return null;
        }
        taken++;
        nextFrame = stamp.frameIndex() + every;
        nextQpcNs = stamp.qpcNs() + intervalNs;
        inFlight++;
        return new Frame(taken, String.format("frame-%05d.png", taken), stamp.frameIndex(),
            sinceReload, stamp.qpcNs(), stamp.swapQpcNs());
    }

    /** The frame's readback arrived; a writer takes it next. */
    public synchronized void arrived(Frame frame) {
        inFlight--;
        writing++;
    }

    /**
     * Wait while `max` frames or more are pending, as long as a writer holds one of them: a
     * readback in flight arrives only through the render thread this call holds, so waiting on
     * one alone would never end (render thread; a stop ends the wait).
     */
    public synchronized void awaitSlot(int max) throws InterruptedException {
        while (stopped == null && inFlight + writing >= max && writing > 0) {
            wait();
        }
    }

    /** Frames taken and not yet written or dropped. */
    public synchronized int pending() {
        return inFlight + writing;
    }

    public synchronized void written(Frame frame, String sha256) {
        writing--;
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("name", frame.name());
        entry.put("sha256", sha256);
        entry.put("frameIndex", frame.frameIndex());
        entry.put("sinceReload", frame.sinceReload());
        entry.put("qpcNs", frame.qpcNs());
        entry.put("swapQpcNs", frame.swapQpcNs());
        frames.add(entry);
        settle();
    }

    /** A taken frame that produced no file; `arrived` tells whether its readback had come. */
    public synchronized void dropped(Frame frame, boolean arrived, String reason) {
        if (arrived) {
            writing--;
        } else {
            inFlight--;
        }
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("name", frame.name());
        entry.put("frameIndex", frame.frameIndex());
        entry.put("reason", reason);
        dropped.add(entry);
        settle();
    }

    /** No frame is taken from now on; the manifest follows the pending frames, marked incomplete. */
    public synchronized void stop(String why) {
        if (stopped == null && !done.isDone()) {
            stopped = why;
        }
        settle();
    }

    public CompletableFuture<Map<String, Object>> done() {
        return done;
    }

    private void settle() {
        notifyAll();
        if (done.isDone() || inFlight + writing > 0 || (stopped == null && taken < count)) {
            return;
        }
        frames.sort((a, b) -> Long.compare((Long) a.get("frameIndex"), (Long) b.get("frameIndex")));
        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("schema", 1);
        manifest.put("complete", stopped == null && dropped.isEmpty());
        manifest.put("stopped", stopped);
        manifest.put("count", count);
        manifest.put(intervalNs > 0 ? "intervalMs" : "every", intervalNs > 0 ? intervalNs / 1e6 : every);
        manifest.put("frames", frames);
        manifest.put("dropped", dropped);
        Path path = folder.resolve(MANIFEST);
        try {
            Files.writeString(path, Json.write(manifest) + "\n");
        } catch (IOException | RuntimeException error) {
            done.completeExceptionally(new IllegalStateException("cannot write " + path + ": " + error, error));
            return;
        }
        Map<String, Object> answer = new LinkedHashMap<>();
        answer.put("frames", List.copyOf(frames));
        answer.put("dropped", List.copyOf(dropped));
        answer.put("manifest", path.toString());
        done.complete(answer);
    }

    /**
     * A new, empty subfolder of `directory` for one attempt: attempt-001, -002, ... the first that
     * does not exist yet, created here (the parent too).
     */
    public static Path attemptFolder(Path directory) throws IOException {
        Files.createDirectories(directory);
        for (int n = 1; n < 100_000; n++) {
            Path folder = directory.resolve(String.format("%s%03d", ATTEMPT, n));
            if (Files.exists(folder)) {
                continue;
            }
            try {
                return Files.createDirectory(folder);
            } catch (FileAlreadyExistsException raced) {
                // another attempt took it first: the next number
            }
        }
        throw new IOException(directory + " holds no free attempt folder");
    }

    /** The file's SHA-256 in lower-case hex. */
    public static String sha256(Path file) {
        try (InputStream stream = Files.newInputStream(file)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[1 << 16];
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
