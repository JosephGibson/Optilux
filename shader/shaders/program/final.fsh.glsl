// final: the display target onto the screen, 26.3's RGBA8 main target (plans/m4.md P15), with the
// static triangular dither of one 8-bit step (lib/dither.glsl; DITHER), opaque.

#include "/lib/options.glsl"
#ifdef DITHER
#include "/lib/dither.glsl"
#endif

uniform sampler2D colortex6;

layout(location = 0) out vec4 screenColor;

void main() {
    vec3 display = texelFetch(colortex6, ivec2(gl_FragCoord.xy), 0).rgb;
#ifdef DITHER
    display = ditherDisplay(display, gl_FragCoord.xy, 255.0);
#endif
    screenColor = vec4(display, 1.0);
}
