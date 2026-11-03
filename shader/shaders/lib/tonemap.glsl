// The display curve and grade: HDR scene light (exposed) to display-linear values in [0, 1].
// The curve has the rational form Lottes proposed for HDR display mapping, per channel:
//   f(x) = x^a / (x^(a d) b + c),
// a the contrast (the toe's power), d < 1 the shoulder (how fast it bends toward white). Its two
// remaining terms are fixed by the two points it must pass: f(midIn) = midOut keeps mid grey where
// it is meant to sit, f(hdrMax) = 1 puts white at hdrMax. Writing u = x^a and v = x^(a d), each
// point gives a line in b and c (v b + c = u / f), so b is the slope between the two points and c
// the rest; above hdrMax the curve is held at 1. Grading (white balance, saturation) is one matrix
// in linear light before it.

#ifndef OPTILUX_TONEMAP
#define OPTILUX_TONEMAP 1

#define CURVE_CONTRAST 1.35
#define CURVE_SHOULDER 0.97
#define CURVE_MID_IN 0.18
#define CURVE_MID_OUT 0.2
#define CURVE_HDR_MAX 16.0
#define GRADE_SATURATION 1.05

// b and c for the curve through (midIn, midOut) and (hdrMax, 1).
vec2 curveTerms(float contrast, float shoulder, float midIn, float midOut, float hdrMax) {
    float uMid = pow(midIn, contrast);
    float vMid = pow(midIn, contrast * shoulder);
    float uMax = pow(hdrMax, contrast);
    float vMax = pow(hdrMax, contrast * shoulder);
    float b = (uMax - uMid / midOut) / (vMax - vMid);
    return vec2(b, uMax - vMax * b);
}

// The curve per channel; NaN and negative light give 0, anything at or past hdrMax gives 1.
vec3 displayCurve(vec3 light, float contrast, float shoulder, vec2 terms, float hdrMax) {
    vec3 x = clamp(light, 0.0, hdrMax);
    x = mix(x, vec3(0.0), isnan(light)); // a boolean mix selects, so NaN never enters the sum
    vec3 u = pow(x, vec3(contrast));
    vec3 v = pow(x, vec3(contrast * shoulder));
    return min(u / (v * terms.x + terms.y), 1.0);
}

// Saturation about Rec. 709 luminance: the identity at 1, grey at 0.
mat3 saturationMatrix(float saturation) {
    vec3 luma = vec3(0.2126, 0.7152, 0.0722) * (1.0 - saturation);
    return mat3(luma.r + saturation, luma.r, luma.r,
                luma.g, luma.g + saturation, luma.g,
                luma.b, luma.b, luma.b + saturation);
}

// Exposed scene light to display-linear: the grade, then the curve at the pack's settings.
vec3 tonemap(vec3 exposed) {
    vec2 terms = curveTerms(CURVE_CONTRAST, CURVE_SHOULDER, CURVE_MID_IN, CURVE_MID_OUT, CURVE_HDR_MAX);
    vec3 graded = saturationMatrix(GRADE_SATURATION) * exposed;
    return displayCurve(graded, CURVE_CONTRAST, CURVE_SHOULDER, terms, CURVE_HDR_MAX);
}

#endif
