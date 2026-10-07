package optilux.helper.mixin;

import net.minecraft.client.Minecraft;
import optilux.helper.Hooks;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * The pause screen refused while `input.block` holds (docs/mod.md#9-input-and-hud). On 26.3
 * Minecraft.pauseGame is the one caller of Gui.setPauseScreen; it serves the Escape key and
 * pauseIfInactive (a lost focus with pauseOnLostFocus, which the harness writes false). And the
 * swap's return (plans/m1.md D26): 26.3 has no Window.updateDisplay; renderFrame, right after
 * GameRenderer.render, presents through GpuSurface.present, which on OpenGL is GlSurface.present
 * calling SDL_GL_SwapWindow.
 */
@Mixin(Minecraft.class)
public abstract class MinecraftMixin {
    @Inject(method = "pauseGame(Z)V", at = @At("HEAD"), cancellable = true)
    private void optilux$refusePause(CallbackInfo info) {
        if (Hooks.inputBlocked()) {
            info.cancel();
        }
    }

    @Inject(method = "renderFrame(Z)V", at = @At(value = "INVOKE",
        target = "Lcom/mojang/renderpearl/api/device/GpuSurface;present()V",
        shift = At.Shift.AFTER))
    private void optilux$swapped(CallbackInfo info) {
        Hooks.swapped();
    }
}
