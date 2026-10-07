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
 * pauseIfInactive (a lost focus with pauseOnLostFocus, which the harness writes false).
 */
@Mixin(Minecraft.class)
public abstract class MinecraftMixin {
    @Inject(method = "pauseGame(Z)V", at = @At("HEAD"), cancellable = true)
    private void optilux$refusePause(CallbackInfo info) {
        if (Hooks.inputBlocked()) {
            info.cancel();
        }
    }
}
