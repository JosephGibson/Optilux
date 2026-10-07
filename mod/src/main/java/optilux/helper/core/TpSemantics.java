package optilux.helper.core;

import java.math.BigDecimal;

/**
 * What `/tp x y z yaw pitch` does to a pose on 26.3, implemented once, here (docs/lessons.md#game-control:
 * never in the harness). Read in the pinned client jar: WorldCoordinate.parseDouble adds 0.5 to an
 * absolute coordinate written without a '.' when centre correction is on, and
 * WorldCoordinates.parseDouble turns it on for x and z only, never y; RotationArgument reads both
 * angles without it and getRotation casts each to float; TeleportCommand.performTeleport passes
 * both through Mth.wrapDegrees; Entity.setXRot stores Math.clamp(pitch % 360, -90, 90).
 */
public final class TpSemantics {
    private TpSemantics() {
    }

    /** A pose as the game holds it: position in doubles, angles in floats. */
    public record Pose(double x, double y, double z, float yaw, float pitch) {
    }

    /**
     * The pose `/tp` reaches from these arguments; {@code xInteger} and {@code zInteger} say whether
     * that coordinate was written as an integer literal (no '.', no exponent).
     */
    public static Pose apply(double x, boolean xInteger, double y, double z, boolean zInteger,
        double yaw, double pitch) {
        return new Pose(xInteger ? x + 0.5 : x, y, zInteger ? z + 0.5 : z,
            wrapDegrees((float) yaw), clampPitch(wrapDegrees((float) pitch)));
    }

    /** Mth.wrapDegrees(float) of 26.3: 180 -> -180, the range [-180, 180). */
    public static float wrapDegrees(float degrees) {
        float wrapped = degrees % 360.0f;
        if (wrapped >= 180.0f) {
            wrapped -= 360.0f;
        }
        if (wrapped < -180.0f) {
            wrapped += 360.0f;
        }
        return wrapped;
    }

    /**
     * A coordinate written for a command: plain decimal with a '.', so `/tp` adds no centre
     * correction and brigadier's readDouble, which takes no exponent, reads it.
     */
    public static String literal(double value) {
        String text = BigDecimal.valueOf(value).toPlainString();
        return text.contains(".") ? text : text + ".0";
    }

    /** Entity.setXRot's stored value: the pitch modulo 360, clamped to [-90, 90]. */
    public static float clampPitch(float pitch) {
        return Math.clamp(pitch % 360.0f, -90.0f, 90.0f);
    }
}
