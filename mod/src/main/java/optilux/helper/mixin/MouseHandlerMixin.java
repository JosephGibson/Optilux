package optilux.helper.mixin;

import net.minecraft.client.MouseHandler;
import optilux.helper.Hooks;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * `input.block`'s mouse half (docs/mod.md#9-input-and-hud). On 26.3 SDLEventHandler hands every
 * mouse event to these three methods; onMove takes both the relative motion of SDL3's relative
 * mode (the grabbed mouse, raw input) and the absolute cursor, so cancelling at its HEAD blocks both.
 */
@Mixin(MouseHandler.class)
public abstract class MouseHandlerMixin {
    @Inject(method = "onMove(JDDDD)V", at = @At("HEAD"), cancellable = true)
    private void optilux$blockMove(CallbackInfo info) {
        if (Hooks.inputBlocked()) {
            info.cancel();
        }
    }

    @Inject(method = "onButton(JLnet/minecraft/client/input/MouseButtonInfo;I)V", at = @At("HEAD"),
        cancellable = true)
    private void optilux$blockButton(CallbackInfo info) {
        if (Hooks.inputBlocked()) {
            info.cancel();
        }
    }

    @Inject(method = "onScroll(JDD)V", at = @At("HEAD"), cancellable = true)
    private void optilux$blockScroll(CallbackInfo info) {
        if (Hooks.inputBlocked()) {
            info.cancel();
        }
    }
}
