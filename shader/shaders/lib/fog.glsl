// The edge fog: the end of the render distance faded into the sky behind it. As 26.3's own edge
// fog it runs over the larger of the horizontal and the vertical distance from the camera, and
// ends at `far` (render distance x 16) after a band a tenth of `far` wide, kept between 4 and 64
// blocks. The environment's fogs (weather, water, lava: fogStart and fogEnd) are M5's analytic fogs.

#ifndef OPTILUX_FOG
#define OPTILUX_FOG 1

// The distance the edge fog runs over, from a position relative to the camera.
float edgeDistance(vec3 fromCamera) {
    return max(length(fromCamera.xz), abs(fromCamera.y));
}

// None before the band, all from `far` on, a straight ramp across the band.
float edgeFog(float distance, float far) {
    float band = clamp(far * 0.1, 4.0, 64.0);
    return clamp((distance - (far - band)) / band, 0.0, 1.0);
}

#endif
