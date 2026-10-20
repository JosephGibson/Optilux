package optilux.helper;

import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import java.util.stream.Stream;
import javax.imageio.ImageIO;
import optilux.helper.core.Capture;
import optilux.helper.core.Errors;
import optilux.helper.core.FrameClock;
import optilux.helper.core.Protocol;
import optilux.helper.core.Readiness;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * `selftest` (docs/mod.md#11-build-and-test, A10): each capability tried in the game, pass or fail
 * with what was seen. frameClock: frames advance, qpcNs rises and the swap stamp lies between two
 * frame heads; renderer: the readiness reading is taken and the renderer has sections; reload: a
 * real Iris reload, after which Iris's frame counter equals the frames since reloadFrame; capture:
 * one frame into a temporary folder, ready-triggered and aligned (plans/m3.md D61), its file equal
 * to the manifest's sha256 and decoded at the main target's size, its counter the frames since the
 * reload check's reloadFrame and at the phase, the first frame at the phase from the frame that
 * found the predicate held, within CAPTURE_LIMIT_SECONDS, then deleted; input: the
 * input mixins applied (the block's state is reported). It holds the capture resource and counts
 * as mutating (it reloads), so it never runs inside a measurement; `not-ready` before a world.
 */
final class Selftest {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    /** Frames the clock check waits for; the swap before the last head follows the first head. */
    private static final int CLOCK_FRAMES = 3;
    private static final List<String> INPUT_MIXINS = List.of("KeyboardHandlerMixin",
        "MouseHandlerMixin", "MinecraftMixin");
    /** The capture's ready wait: the session start's 10 stable frames (optilux/session.py). */
    static final int STABLE_FRAMES = 10;
    /** The capture's phase: a frame at any counter hits it once in four. */
    static final Capture.Align ALIGN = new Capture.Align(4, 1);
    /** The capture's own bound, inside the session's 120 s selftest timeout (optilux/session.py). */
    static final int CAPTURE_LIMIT_SECONDS = 60;

    private final FrameClock clock;
    private final BooleanSupplier inWorld;
    private final BooleanSupplier inputBlocked;
    private final RendererAdapter renderer;
    private final IrisAdapter iris;
    private final CaptureAdapter capture;

    Selftest(FrameClock clock, BooleanSupplier inWorld, BooleanSupplier inputBlocked,
        RendererAdapter renderer, IrisAdapter iris, CaptureAdapter capture) {
        this.clock = clock;
        this.inWorld = inWorld;
        this.inputBlocked = inputBlocked;
        this.renderer = renderer;
        this.iris = iris;
        this.capture = capture;
    }

    Map<String, Protocol.Handler> handlers() {
        return Map.of("selftest", this::selftest);
    }

    private Map<String, Object> selftest(Protocol.Request request) throws Exception {
        if (!inWorld.getAsBoolean()) {
            throw new Errors.Refused(Errors.NOT_READY, "selftest needs a world; fix: world.wait first");
        }
        Map<String, Object> checks = new LinkedHashMap<>();
        checks.put("frameClock", check(this::frameClock));
        checks.put("renderer", check(this::rendererProbe));
        Map<String, Object> reload = check(() -> reload(request));
        checks.put("reload", reload);
        Long reloadFrame = reload.get("reloadFrame") instanceof Long frame ? frame : null;
        checks.put("capture", check(() -> captureToTemp(request, reloadFrame)));
        checks.put("input", check(this::input));
        boolean pass = checks.values().stream()
            .allMatch(c -> Boolean.TRUE.equals(((Map<?, ?>) c).get("pass")));
        LOG.info("optilux-helper: selftest {}: {}", pass ? "passed" : "failed", checks);
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("pass", pass);
        found.put("checks", checks);
        return found;
    }

    @FunctionalInterface
    private interface Check {
        Map<String, Object> run() throws Exception;
    }

    /** One check's fields with its pass; a check that throws fails with the error. */
    private static Map<String, Object> check(Check check) throws InterruptedException {
        try {
            return check.run();
        } catch (InterruptedException interrupted) {
            throw interrupted;
        } catch (Exception error) {
            Map<String, Object> found = new LinkedHashMap<>();
            found.put("pass", false);
            found.put("error", error.getClass().getSimpleName() + ": " + error.getMessage());
            return found;
        }
    }

    private Map<String, Object> frameClock() throws Exception {
        FrameClock.Stamp first = clock.last();
        iris.awaitFrame(first.frameIndex() + CLOCK_FRAMES);
        FrameClock.Stamp later = clock.last();
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("pass", later.frameIndex() > first.frameIndex() && later.qpcNs() > first.qpcNs()
            && later.swapQpcNs() > first.qpcNs() && later.swapQpcNs() <= later.qpcNs());
        found.put("first", stamp(first));
        found.put("later", stamp(later));
        return found;
    }

    private Map<String, Object> rendererProbe() throws Exception {
        Readiness.Reading reading = Tasks.onRender(renderer::reading);
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("pass", reading.sections() > 0);
        found.put("reading", RendererAdapter.describe(reading));
        return found;
    }

    private Map<String, Object> reload(Protocol.Request request) throws Exception {
        IrisAdapter.Reloaded reloaded = iris.reload(request, CLOCK_FRAMES);
        if (reloaded == null) {
            throw new InterruptedException("selftest was answered first");
        }
        // Between frames on the render thread, so neither counter is mid-frame.
        long[] counters = Tasks.onRender(() -> new long[] {clock.last().frameIndex(), iris.sinceReload()});
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("pass", reloaded.pack() != null
            && counters[1] == counters[0] - reloaded.reloadFrame());
        found.put("pack", reloaded.pack());
        found.put("pipeline", reloaded.pipeline());
        found.put("seconds", reloaded.seconds());
        found.put("reloadFrame", reloaded.reloadFrame());
        found.put("frameIndex", counters[0]);
        found.put("sinceReload", counters[1]);
        return found;
    }

    /**
     * The capture check; `reloadFrame` from the reload check (null when it failed), so the
     * frame's counter is judged against the frame clock, not only by the capture's own filter.
     */
    private Map<String, Object> captureToTemp(Protocol.Request request, Long reloadFrame)
        throws Exception {
        Path directory = Files.createTempDirectory("optilux-selftest-");
        try {
            Capture shot = new Capture(Capture.attemptFolder(directory), 1, 1, 0, ALIGN,
                new Readiness(STABLE_FRAMES, 0, System.nanoTime()), true);
            CompletableFuture.delayedExecutor(CAPTURE_LIMIT_SECONDS, TimeUnit.SECONDS).execute(
                () -> shot.stop("no frame within " + CAPTURE_LIMIT_SECONDS + " s"));
            Map<String, Object> answer = capture.run(shot, request::live);
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> frames = (List<Map<String, Object>>) answer.get("frames");
            Map<?, ?> ready = (Map<?, ?>) answer.get("ready");
            if (frames.isEmpty()) {
                Map<String, Object> found = new LinkedHashMap<>();
                found.put("pass", false);
                found.put("error", "no frame within " + CAPTURE_LIMIT_SECONDS + " s; ready "
                    + (ready == null ? "never held" : "held: " + ready));
                return found;
            }
            Map<String, Object> frame = frames.get(0);
            long frameIndex = (Long) frame.get("frameIndex");
            Long counter = (Long) frame.get("sinceReload");
            boolean aligned = counter != null && reloadFrame != null
                && counter == frameIndex - reloadFrame && ALIGN.holds(counter);
            boolean first = ready != null && frameIndex >= (Long) ready.get("frameIndex")
                && frameIndex < (Long) ready.get("frameIndex") + ALIGN.cycle();
            Path file = Path.of((String) answer.get("manifest")).resolveSibling((String) frame.get("name"));
            BufferedImage image = ImageIO.read(file.toFile());
            int[] size = Tasks.onRender(() -> new int[] {
                Tasks.minecraft().gameRenderer.mainRenderTarget().width,
                Tasks.minecraft().gameRenderer.mainRenderTarget().height});
            Map<String, Object> found = new LinkedHashMap<>();
            found.put("pass", Capture.sha256(file).equals(frame.get("sha256")) && image != null
                && image.getWidth() == size[0] && image.getHeight() == size[1] && aligned && first);
            found.put("frameIndex", frameIndex);
            found.put("sinceReload", counter);
            found.put("reloadFrame", reloadFrame);
            found.put("align", ALIGN.fields());
            found.put("ready", ready);
            found.put("size", image == null ? null : image.getWidth() + "x" + image.getHeight());
            found.put("target", size[0] + "x" + size[1]);
            return found;
        } finally {
            delete(directory);
        }
    }

    private Map<String, Object> input() {
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("pass", MixinGate.APPLIED.containsAll(INPUT_MIXINS));
        found.put("mixins", INPUT_MIXINS.stream().filter(MixinGate.APPLIED::contains).toList());
        found.put("blocked", inputBlocked.getAsBoolean());
        return found;
    }

    private static Map<String, Object> stamp(FrameClock.Stamp stamp) {
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("frameIndex", stamp.frameIndex());
        found.put("qpcNs", stamp.qpcNs());
        found.put("swapQpcNs", stamp.swapQpcNs());
        return found;
    }

    private static void delete(Path directory) {
        try (Stream<Path> paths = Files.walk(directory)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        } catch (IOException error) {
            LOG.warn("optilux-helper: selftest left {}: {}", directory, error.toString());
        }
    }
}
