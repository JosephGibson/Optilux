// The fragment stage of the forward programs, drawn into the scene with the draw's own blend.
// After deferred they land on the lit scene (water, translucent terrain, clouds, weather); a draw
// they take before deferred is overwritten by it until M4.P07 gives it its own program (D76).
// Unlit, they draw vertex colour times texture; FORWARD_LIT lights them with the shared include,
// facing up and unshadowed until M4.P07's forward lighting. Both fade into the sky with the edge
// fog at their own distance.
// Switches: FORWARD_TEXTURE, FORWARD_LIT, and FORWARD_NOT_IN_BENCH: nothing under
// BENCH_DETERMINISTIC (clouds drift with the game time, which no command sets; weather and
// lightning move with the ticks before /tick freeze and the stepped ones).

#include "/lib/options.glsl"
#include "/lib/srgb.glsl"
#include "/lib/fog.glsl"
#include "/program/scene.glsl"

in vec4 vertexColor;
in vec3 fromCamera;

// Iris's cutoff for this draw (program/surface.fsh.glsl).
uniform float alphaTestRef;
uniform float far;

#ifdef FORWARD_TEXTURE
uniform sampler2D gtexture;
in vec2 albedoCoord;
#endif

#ifdef FORWARD_LIT
in vec2 levels;
#endif

/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 sceneOut;

void main() {
#if defined FORWARD_NOT_IN_BENCH && defined BENCH_DETERMINISTIC
    discard;
#endif
    vec4 color = vertexColor;
    float coverage = vertexColor.a;
#ifdef FORWARD_TEXTURE
    vec4 texel = texture(gtexture, albedoCoord);
    coverage = texel.a;
    color *= texel;
#endif
    if (coverage < alphaTestRef && alphaTestRef <= 1.0) discard;
    vec3 light = linearFromSrgb(color.rgb);
#ifdef FORWARD_LIT
    vec2 lit = sceneLevels(levels, length(fromCamera));
    light = surfaceRadiance(light, vec3(0.0, 1.0, 0.0), lit, 1.0, 1.0, toSceneLight(),
                            sceneLightColor(), sceneSkyColor(), BLOCK_COLOR, FLOOR_COLOR);
#endif
    float fog = edgeFog(edgeDistance(fromCamera), far);
    sceneOut = vec4(mix(light, sceneSky(normalize(fromCamera)), fog), color.a);
}
