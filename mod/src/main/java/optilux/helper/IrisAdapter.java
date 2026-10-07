package optilux.helper;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BiConsumer;
import java.util.function.BooleanSupplier;
import net.irisshaders.iris.Iris;
import net.irisshaders.iris.pipeline.WorldRenderingPipeline;
import net.irisshaders.iris.shaderpack.ShaderPack;
import net.irisshaders.iris.shaderpack.option.values.OptionValues;
import net.irisshaders.iris.uniforms.SystemTimeUniforms;
import optilux.helper.core.Errors;
import optilux.helper.core.FrameClock;
import optilux.helper.core.Protocol;
import optilux.helper.core.ReloadOutcome;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The Iris 1.11.7 shader-loader adapter (docs/mod.md#4-architecture; targets in
 * docs/platform.md#mod-adapter-surface, each read in the pinned jar): `shaders.reload`,
 * `shaders.options`, sinceReload for every answer and event, and the reload events. Iris.reload
 * runs on the render thread: it re-reads iris.properties and the pack's settings file, destroys
 * the pipeline and, in a world, creates the new one at once (preparePipeline), which resets
 * SystemTimeUniforms.COUNTER; a load failure goes through handleException, hooked here (F5).
 */
final class IrisAdapter {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");

    /** One reload that loaded: the pack, the pipeline, Iris.reload's duration, its frame. */
    record Reloaded(String pack, String pipeline, double seconds, long reloadFrame) {
    }

    private record FrameWait(long frameIndex, CompletableFuture<Long> reached) {
    }

    private final FrameClock clock;
    private final BooleanSupplier inWorld;
    private final BiConsumer<String, Map<String, Object>> events;
    private final List<FrameWait> waits = new CopyOnWriteArrayList<>();
    // A reload runs from Iris.reload until its frames after: a second one would reset the counter
    // under the first's reloadFrame.
    private final AtomicBoolean reloadRunning = new AtomicBoolean();
    // Render thread only: whether a reload of ours runs, and the failure Iris handed over in it.
    private boolean reloading;
    private Exception hooked;

    IrisAdapter(FrameClock clock, BooleanSupplier inWorld, BiConsumer<String, Map<String, Object>> events) {
        this.clock = clock;
        this.inWorld = inWorld;
        this.events = events;
    }

    Map<String, Protocol.Handler> handlers() {
        Map<String, Protocol.Handler> found = new LinkedHashMap<>();
        found.put("shaders.reload", this::shadersReload);
        found.put("shaders.options", this::shadersOptions);
        return found;
    }

    /** Frames since the last pipeline creation: Iris's own frameCounter (any thread). */
    long sinceReload() {
        return SystemTimeUniforms.COUNTER.getAsInt();
    }

    /** Iris.handleException HEAD (render thread, where the load runs). */
    void failed(Exception error) {
        if (reloading) {
            if (hooked == null) {
                hooked = error;
            }
        } else {
            LOG.warn("optilux-helper: Iris failed to load a pack outside shaders.reload: {}",
                error.toString());
        }
    }

    /** At every frame head: frame waits that are due complete. */
    void frame() {
        long index = clock.last().frameIndex();
        for (FrameWait wait : waits) {
            if (index >= wait.frameIndex() && wait.reached().complete(index)) {
                waits.remove(wait);
            }
        }
    }

    /** Wait until frame `frameIndex` has begun (the request's timeout interrupts). */
    long awaitFrame(long frameIndex) throws Exception {
        FrameWait wait = new FrameWait(frameIndex, new CompletableFuture<>());
        waits.add(wait);
        try {
            if (clock.last().frameIndex() >= frameIndex) {
                wait.reached().complete(clock.last().frameIndex());
            }
            return Tasks.unwrap(wait.reached());
        } finally {
            waits.remove(wait);
        }
    }

    private Map<String, Object> shadersReload(Protocol.Request request) throws Exception {
        int framesAfter = Math.toIntExact((Long) request.args().get("framesAfter"));
        Reloaded reloaded = reload(request, framesAfter);
        if (reloaded == null) {
            return null;
        }
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("pack", reloaded.pack());
        found.put("pipeline", reloaded.pipeline());
        found.put("seconds", reloaded.seconds());
        found.put("framesAfter", framesAfter);
        found.put("reloadFrame", reloaded.reloadFrame());
        return found;
    }

    /**
     * Reload and wait until the new pipeline rendered `framesAfter` frames (frame reloadFrame +
     * framesAfter + 1 began); `busy` while another reload runs. Null when the request was answered
     * first.
     */
    Reloaded reload(Protocol.Request request, int framesAfter) throws Exception {
        if (!reloadRunning.compareAndSet(false, true)) {
            throw new Errors.Refused(Errors.BUSY, "a shader reload is running");
        }
        try {
            Reloaded reloaded = reloadNow(request);
            if (reloaded != null) {
                awaitFrame(reloaded.reloadFrame() + framesAfter + 1);
            }
            return reloaded;
        } finally {
            reloadRunning.set(false);
        }
    }

    /**
     * Iris.reload on the render thread, between frames: the outcome mapped (ReloadOutcome), the
     * events sent. reloadFrame is the last frame of the old pipeline, so frame reloadFrame + k is
     * the new pipeline's k-th and sees sinceReload k.
     */
    private Reloaded reloadNow(Protocol.Request request) throws Exception {
        return Tasks.onRender(() -> {
            if (!inWorld.getAsBoolean()) {
                throw new Errors.Refused(Errors.NOT_READY, "not in a world; fix: world.wait first");
            }
            if (Tasks.skippedLate(request)) {
                return null;
            }
            hooked = null;
            reloading = true;
            Throwable thrown = null;
            long start = System.nanoTime();
            try {
                Iris.reload();
            } catch (Throwable error) {
                thrown = error;
            } finally {
                reloading = false;
            }
            double seconds = (System.nanoTime() - start) / 1e9;
            Exception error = hooked;
            hooked = null;
            String wanted = Iris.getIrisConfig().getShaderPackName().orElse("(none)");
            Errors.Refused refused = ReloadOutcome.of(error, thrown, Iris.isFallback(), wanted);
            if (refused != null) {
                LOG.warn("optilux-helper: shaders.reload of {} failed in {} s: {} {}", wanted,
                    seconds, refused.code(), refused.getMessage());
                events.accept("reload.failed", Map.of("message", refused.getMessage()));
                throw refused;
            }
            Reloaded reloaded = new Reloaded(Iris.getCurrentPackName(), pipeline(), seconds,
                clock.last().frameIndex());
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("pack", reloaded.pack());
            data.put("pipeline", reloaded.pipeline());
            data.put("seconds", reloaded.seconds());
            events.accept("reload.done", data);
            LOG.info("optilux-helper: shaders.reload: {} ({}) in {} s after frame {}",
                reloaded.pack(), reloaded.pipeline(), seconds, reloaded.reloadFrame());
            return reloaded;
        });
    }

    private Map<String, Object> shadersOptions(Protocol.Request request) throws Exception {
        return Tasks.onRender(() -> {
            ShaderPack pack = Iris.getCurrentPack().orElse(null);
            if (pack == null) {
                throw new Errors.Refused(Errors.FAILED, "no shader pack is active ("
                    + Iris.getCurrentPackName() + "); fix: select one in iris.properties, then"
                    + " shaders.reload");
            }
            Map<String, Object> found = new LinkedHashMap<>();
            found.put("pack", Iris.getCurrentPackName());
            found.put("values", values(pack.getShaderPackOptions().getOptionValues()));
            return found;
        });
    }

    /** Every option of the pack at its effective value: the set one, else the pack's default. */
    static Map<String, Object> values(OptionValues values) {
        Map<String, Object> found = new TreeMap<>();
        for (String name : values.getOptionSet().getBooleanOptions().keySet()) {
            found.put(name, values.getBooleanValueOrDefault(name));
        }
        for (String name : values.getOptionSet().getStringOptions().keySet()) {
            found.put(name, values.getStringValueOrDefault(name));
        }
        return found;
    }

    /** The active pipeline's kind (IrisRenderingPipeline, or VanillaRenderingPipeline when off). */
    private static String pipeline() {
        WorldRenderingPipeline pipeline = Iris.getPipelineManager().getPipelineNullable();
        return pipeline == null ? null : pipeline.getClass().getSimpleName();
    }
}
