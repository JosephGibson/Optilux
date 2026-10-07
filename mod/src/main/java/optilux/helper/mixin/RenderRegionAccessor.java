package optilux.helper.mixin;

import net.caffeinemc.mods.sodium.client.render.chunk.RenderSection;
import net.caffeinemc.mods.sodium.client.render.chunk.region.RenderRegion;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** Sodium 0.9.2's render region: its section slots (null where no section is loaded). */
@Mixin(RenderRegion.class)
public interface RenderRegionAccessor {
    @Accessor("sections")
    RenderSection[] optilux$sections();
}
