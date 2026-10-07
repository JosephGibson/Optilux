package optilux.helper.mixin;

import net.minecraft.client.renderer.GameRenderer;
import optilux.helper.Hooks;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * The frame hook at HEAD of GameRenderer.render, and the capture point (docs/mod.md#8-capture):
 * on 26.3 render() calls renderLevel, tryTakeScreenshotIfNeeded, LevelRenderer.blitEntityOutline
 * and applyPostEffects only when the level renders, then the GUI; right after applyPostEffects the
 * world, Iris's final pass and the post effects are in the main target and the GUI is not.
 */
@Mixin(GameRenderer.class)
public abstract class GameRendererMixin {
    @Inject(method = "render()V", at = @At("HEAD"))
    private void optilux$frameHead(CallbackInfo info) {
        Hooks.frameHead();
    }

    @Inject(method = "render()V", at = @At(value = "INVOKE",
        target = "Lnet/minecraft/client/renderer/GameRenderer;applyPostEffects()V",
        shift = At.Shift.AFTER))
    private void optilux$capturePoint(CallbackInfo info) {
        Hooks.capturePoint();
    }
}
