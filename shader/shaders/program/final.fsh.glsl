// final: the display target onto the screen, 26.3's RGBA8 main target (plans/m4.md P15), with the
// static triangular dither of one 8-bit step (lib/dither.glsl), opaque.

#include "/lib/dither.glsl"

uniform sampler2D colortex6;

layout(location = 0) out vec4 screenColor;

void main() {
    vec3 display = texelFetch(colortex6, ivec2(gl_FragCoord.xy), 0).rgb;
    screenColor = vec4(ditherDisplay(display, gl_FragCoord.xy, 255.0), 1.0);
}
