package optilux.helper.mixin;

import java.util.concurrent.ConcurrentLinkedDeque;
import net.caffeinemc.mods.sodium.client.render.chunk.RenderSectionManager;
import net.caffeinemc.mods.sodium.client.render.chunk.async.CullTask;
import net.caffeinemc.mods.sodium.client.render.chunk.lists.DeferredTaskList;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/**
 * Sodium 0.9.2's section manager, read by the readiness predicate (docs/mod.md#7-readiness; each
 * field read by disassembly, docs/platform.md#mod-adapter-surface R7): buildResults, finished jobs
 * not yet uploaded; taskLists, the sections the last cull left to submit (null before the first);
 * pendingTask, the async cull in progress; needsGraphUpdate; and the task counts updateChunks
 * submitted for this frame, the next frame and deferred (reset to 0 at its start).
 */
@Mixin(RenderSectionManager.class)
public interface RenderSectionManagerAccessor {
    @Accessor("buildResults")
    ConcurrentLinkedDeque<?> optilux$buildResults();

    @Accessor("taskLists")
    DeferredTaskList optilux$taskLists();

    @Accessor("pendingTask")
    CullTask optilux$pendingTask();

    @Accessor("needsGraphUpdate")
    boolean optilux$needsGraphUpdate();

    @Accessor("thisFrameBlockingTasks")
    int optilux$thisFrameBlockingTasks();

    @Accessor("nextFrameBlockingTasks")
    int optilux$nextFrameBlockingTasks();

    @Accessor("deferredTasks")
    int optilux$deferredTasks();
}
