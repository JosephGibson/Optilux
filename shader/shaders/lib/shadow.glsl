// The shadow map's mapping (plans/m4.md D77; docs/research/shadows.md#distorted-single-map-culled):
// Iris renders one orthographic map centred on the camera, `distance` blocks to each side. A
// radial distortion spends its texels near the centre: a point at radius r (the map's normalized
// coordinates, 0 at the camera, 1 at its edge) moves to
//   s(r) = r / (K r + 1 - K),
// which keeps the centre and the edge where they are and magnifies the centre by 1 / (1 - K). Its
// inverse is r = s (1 - K) / (1 - K s). One texel of a map `resolution` wide then covers
//   2 distance / resolution x (K r + 1 - K)^2 / (1 - K)
// blocks at radius r, the size the lookup's offset along the normal scales with.

#ifndef OPTILUX_SHADOW
#define OPTILUX_SHADOW 1

#define SHADOW_DISTORTION 0.8

vec2 shadowDistort(vec2 position) {
    float radius = length(position);
    return position / (SHADOW_DISTORTION * radius + (1.0 - SHADOW_DISTORTION));
}

vec2 shadowUndistort(vec2 distorted) {
    float radius = length(distorted);
    return distorted * ((1.0 - SHADOW_DISTORTION) / (1.0 - SHADOW_DISTORTION * radius));
}

// One texel's width in blocks at radius `radius` of a map `resolution` texels and `distance`
// blocks to each side.
float shadowTexelBlocks(float radius, float distance, float resolution) {
    float stretch = SHADOW_DISTORTION * radius + (1.0 - SHADOW_DISTORTION);
    return 2.0 * distance / resolution * stretch * stretch / (1.0 - SHADOW_DISTORTION);
}

#endif
