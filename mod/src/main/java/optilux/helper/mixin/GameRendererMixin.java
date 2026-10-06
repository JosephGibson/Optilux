package optilux.helper.mixin;

import net.minecraft.client.renderer.GameRenderer;
import optilux.helper.Hooks;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** The frame hook: HEAD of GameRenderer.render (docs/platform.md#mod-adapter-surface). */
@Mixin(GameRenderer.class)
public abstract class GameRendererMixin {
    @Inject(method = "render()V", at = @At("HEAD"))
    private void optilux$frameHead(CallbackInfo info) {
        Hooks.frameHead();
    }
}
