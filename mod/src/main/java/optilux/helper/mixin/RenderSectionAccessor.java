package optilux.helper.mixin;

import java.util.List;
import net.caffeinemc.mods.sodium.client.render.chunk.RenderSection;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/**
 * Sodium 0.9.2's section: its running jobs, added when a task is submitted and removed when its
 * result is collected on the render thread (ChunkJobResult.clearJobFromSection). A worker takes a
 * job from the queue before it counts itself busy (ChunkBuilder$WorkerRunnable.run), so only this
 * list sees a job in that gap (docs/mod.md#7-readiness).
 */
@Mixin(RenderSection.class)
public interface RenderSectionAccessor {
    @Accessor("runningJobs")
    List<?> optilux$runningJobs();
}
