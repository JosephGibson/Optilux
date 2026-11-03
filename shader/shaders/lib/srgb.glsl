// sRGB's transfer function (IEC 61966-2-1) both ways, per channel. Textures and vertex colours
// arrive sRGB-encoded and are lit in linear light; the display wants the encoded values back.
// The power segment is written as 1 + 1.055 (p - 1), equal to 1.055 p - 0.055, so 1 encodes to
// exactly 1 (p is exactly 1 there) where the usual form lands one float step short.

#ifndef OPTILUX_SRGB
#define OPTILUX_SRGB 1

vec3 linearFromSrgb(vec3 encoded) {
    vec3 low = encoded * (1.0 / 12.92);
    vec3 high = pow((max(encoded, 0.0) + 0.055) * (1.0 / 1.055), vec3(2.4));
    return mix(low, high, step(vec3(0.04045), encoded));
}

vec3 srgbFromLinear(vec3 linear) {
    vec3 low = linear * 12.92;
    vec3 high = 1.0 + 1.055 * (pow(max(linear, 0.0), vec3(1.0 / 2.4)) - 1.0);
    return mix(low, high, step(vec3(0.0031308), linear));
}

#endif
