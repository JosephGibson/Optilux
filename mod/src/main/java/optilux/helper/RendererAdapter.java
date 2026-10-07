package optilux.helper;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.BooleanSupplier;
import net.caffeinemc.mods.sodium.client.render.SodiumWorldRenderer;
import net.caffeinemc.mods.sodium.client.render.chunk.RenderSection;
import net.caffeinemc.mods.sodium.client.render.chunk.RenderSectionManager;
import net.caffeinemc.mods.sodium.client.render.chunk.compile.executor.ChunkBuilder;
import net.caffeinemc.mods.sodium.client.render.chunk.lists.DeferredTaskList;
import net.caffeinemc.mods.sodium.client.render.chunk.region.RenderRegion;
import net.minecraft.client.Minecraft;
import optilux.helper.core.Errors;
import optilux.helper.core.Protocol;
import optilux.helper.core.Readiness;
import optilux.helper.mixin.RenderRegionAccessor;
import optilux.helper.mixin.RenderSectionAccessor;
import optilux.helper.mixin.RenderSectionManagerAccessor;
import optilux.helper.mixin.SodiumWorldRendererAccessor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The Sodium 0.9.2 renderer adapter: `ready` (docs/mod.md#7-readiness). While a wait runs, the
 * frame poll reads the renderer once per frame on the render thread, which owns every field read
 * (each read by disassembly of the pinned jar and listed in the mixin-target test): the builder's
 * queue and busy threads through its public methods, the section manager's build results, task
 * lists, cull task, graph flag and submitted-task counts through accessors, and every loaded
 * section's running jobs. Sodium's own isTerrainRenderComplete is read beside them.
 */
final class RendererAdapter {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");

    private record Wait(Readiness readiness, CompletableFuture<Map<String, Object>> answer) {
    }

    private final BooleanSupplier inWorld;
    private final List<Wait> waits = new CopyOnWriteArrayList<>();

    RendererAdapter(BooleanSupplier inWorld) {
        this.inWorld = inWorld;
    }

    Map<String, Protocol.Handler> handlers() {
        return Map.of("ready", this::ready);
    }

    /** At every frame head: one reading judged by every running wait. */
    void frame() {
        if (waits.isEmpty()) {
            return;
        }
        Readiness.Reading reading = reading();
        long now = System.nanoTime();
        for (Wait wait : waits) {
            Map<String, Object> answer = wait.readiness().frame(reading, now);
            if (answer != null && wait.answer().complete(answer)) {
                waits.remove(wait);
            }
        }
    }

    private Map<String, Object> ready(Protocol.Request request) throws Exception {
        if (!inWorld.getAsBoolean()) {
            throw new Errors.Refused(Errors.NOT_READY, "not in a world; fix: world.wait first");
        }
        int stableFrames = Math.toIntExact((Long) request.args().get("stableFrames"));
        double minSeconds = (Double) request.args().get("minSeconds");
        Wait wait = new Wait(new Readiness(stableFrames, minSeconds, System.nanoTime()),
            new CompletableFuture<>());
        waits.add(wait);
        try {
            Map<String, Object> answer = Tasks.unwrap(wait.answer());
            LOG.info("optilux-helper: ready: {}", answer);
            return answer;
        } catch (InterruptedException interrupted) {
            LOG.info("optilux-helper: ready ended unanswered: {}", wait.readiness().describe());
            throw interrupted;
        } finally {
            waits.remove(wait);
        }
    }

    /** The renderer now (render thread): the predicate's terms and Sodium's own check. */
    Readiness.Reading reading() {
        Minecraft minecraft = Tasks.minecraft();
        boolean world = inWorld.getAsBoolean();
        boolean noScreen = minecraft.gui.screen() == null && minecraft.gui.overlay() == null;
        SodiumWorldRenderer renderer = SodiumWorldRenderer.instanceNullable();
        RenderSectionManager manager = renderer == null ? null
            : ((SodiumWorldRendererAccessor) renderer).optilux$renderSectionManager();
        if (manager == null) {
            return new Readiness.Reading(world, noScreen, 0, 0, 0, 0, 0, -1, 0, false, false);
        }
        ChunkBuilder builder = manager.getBuilder();
        RenderSectionManagerAccessor fields = (RenderSectionManagerAccessor) manager;
        DeferredTaskList taskLists = fields.optilux$taskLists();
        int submitted = fields.optilux$thisFrameBlockingTasks()
            + fields.optilux$nextFrameBlockingTasks() + fields.optilux$deferredTasks();
        boolean graphClean = !fields.optilux$needsGraphUpdate() && fields.optilux$pendingTask() == null;
        return new Readiness.Reading(world, noScreen, manager.getTotalSections(),
            builder.isBuildQueueEmpty() ? 0 : Math.max(1, builder.getScheduledJobCount()),
            builder.getBusyThreadCount(), fields.optilux$buildResults().size(),
            runningJobs(manager), taskLists == null ? -1 : taskLists.size(), submitted, graphClean,
            renderer.isTerrainRenderComplete());
    }

    /** Sections holding a job whose result was not collected yet. */
    private static int runningJobs(RenderSectionManager manager) {
        int found = 0;
        for (RenderRegion region : manager.regions.getLoadedRegions()) {
            for (RenderSection section : ((RenderRegionAccessor) region).optilux$sections()) {
                if (section != null && !((RenderSectionAccessor) section).optilux$runningJobs().isEmpty()) {
                    found++;
                }
            }
        }
        return found;
    }

    /** The reading as fields, for selftest's renderer probe. */
    static Map<String, Object> describe(Readiness.Reading reading) {
        Map<String, Object> found = new LinkedHashMap<>(reading.fields());
        found.put("failing", reading.failing());
        return found;
    }
}
