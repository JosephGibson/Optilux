package optilux.helper.mixin;

import net.minecraft.client.KeyboardHandler;
import optilux.helper.Hooks;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * `input.block`'s keyboard half (docs/mod.md#9-input-and-hud). On 26.3 SDLEventHandler hands key
 * events to keyPress, typed text to textInput (which calls charTyped) and IME composition to
 * textEditing; cancelling all three at HEAD leaves no key path into the game.
 */
@Mixin(KeyboardHandler.class)
public abstract class KeyboardHandlerMixin {
    @Inject(method = "keyPress(JILnet/minecraft/client/input/KeyEvent;)V", at = @At("HEAD"),
        cancellable = true)
    private void optilux$blockKey(CallbackInfo info) {
        if (Hooks.inputBlocked()) {
            info.cancel();
        }
    }

    @Inject(method = "textInput(JLjava/lang/String;)V", at = @At("HEAD"), cancellable = true)
    private void optilux$blockText(CallbackInfo info) {
        if (Hooks.inputBlocked()) {
            info.cancel();
        }
    }

    @Inject(method = "textEditing(JLnet/minecraft/client/input/PreeditEvent;)V", at = @At("HEAD"),
        cancellable = true)
    private void optilux$blockEditing(CallbackInfo info) {
        if (Hooks.inputBlocked()) {
            info.cancel();
        }
    }
}
