#!/usr/bin/env python3
"""Lent Light - ai-happy-01 entry (pure stdlib, deterministic).

Draws a flat-illustration night scene: a small round robot lends the
golden light of its heart to a tired firefly that flew a long way.
No model, no network, no randomness beyond a fixed-seed LCG.
Writes one 1024x1024 PNG to $MAKEFUN_OUTPUT_DIR/entry.png
(or /output/entry.png when the variable is unset).
"""
import binascii
import math
import os
import struct
import zlib

W = 1024
H = 1024

# ---------- palette ----------
SKY_TOP = (19, 24, 40)
SKY_BOT = (47, 61, 96)
MOON = (255, 233, 184)
GOLD = (255, 196, 107)
GOLD_DEEP = (255, 157, 77)
GOLD_PALE = (255, 233, 176)
CREAM = (247, 234, 210)
CREAM_SHADE = (232, 211, 174)
CREAM_DARK = (214, 190, 150)
PANEL = (255, 246, 224)
INK = (43, 42, 51)
CORAL = (242, 161, 140)
HILL_FAR = (16, 21, 42)
HILL_NEAR = (21, 28, 51)
GRASS = (34, 44, 74)
WING = (207, 228, 255)


def _lcg(seed):
    """Fixed-seed generator: deterministic star placement."""
    s = seed
    while True:
        s = (1103515245 * s + 12345) & 0x7FFFFFFF
        yield s


class Canvas:
    """RGB canvas as three bytearray planes; span fills are C-speed."""

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.r = bytearray(w * h)
        self.g = bytearray(w * h)
        self.b = bytearray(w * h)
        self._lut_cache = {}

    def _luts(self, color, alpha):
        key = (color, round(alpha, 4))
        hit = self._lut_cache.get(key)
        if hit is not None:
            return hit
        a = alpha
        luts = tuple(
            bytes(round(color[i] * a + j * (1.0 - a)) for j in range(256))
            for i in range(3)
        )
        self._lut_cache[key] = luts
        return luts

    def span(self, y, x0, x1, color, alpha=1.0):
        if y < 0 or y >= self.h or x1 <= x0:
            return
        x0 = max(0, int(x0))
        x1 = min(self.w, int(x1))
        if x1 <= x0:
            return
        base = y * self.w
        n = x1 - x0
        if alpha >= 1.0:
            self.r[base + x0:base + x1] = bytes([color[0]]) * n
            self.g[base + x0:base + x1] = bytes([color[1]]) * n
            self.b[base + x0:base + x1] = bytes([color[2]]) * n
        else:
            lr, lg, lb = self._luts(color, alpha)
            self.r[base + x0:base + x1] = self.r[base + x0:base + x1].translate(lr)
            self.g[base + x0:base + x1] = self.g[base + x0:base + x1].translate(lg)
            self.b[base + x0:base + x1] = self.b[base + x0:base + x1].translate(lb)

    def rect(self, x, y, w, h, color, alpha=1.0):
        for yy in range(int(y), int(y + h)):
            self.span(yy, x, x + w, color, alpha)

    def circle(self, cx, cy, rad, color, alpha=1.0):
        r = int(math.ceil(rad))
        for y in range(int(cy) - r, int(cy) + r + 1):
            dy = y - cy
            dx2 = rad * rad - dy * dy
            if dx2 < 0:
                continue
            dx = int(math.sqrt(dx2))
            self.span(y, cx - dx, cx + dx + 1, color, alpha)

    def ellipse(self, cx, cy, rx, ry, color, alpha=1.0):
        r = int(math.ceil(ry))
        for y in range(int(cy) - r, int(cy) + r + 1):
            dy = (y - cy) / ry
            dx2 = 1.0 - dy * dy
            if dx2 < 0:
                continue
            dx = int(rx * math.sqrt(dx2))
            self.span(y, cx - dx, cx + dx + 1, color, alpha)

    def polygon(self, pts, color, alpha=1.0):
        ys = [p[1] for p in pts]
        ymin = max(0, int(min(ys)))
        ymax = min(self.h - 1, int(max(ys)))
        n = len(pts)
        for y in range(ymin, ymax + 1):
            xs = []
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    t = (y + 0.5 - y0) / (y1 - y0)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for j in range(0, len(xs) - 1, 2):
                self.span(y, xs[j], xs[j + 1] + 1, color, alpha)

    def thick_line(self, x0, y0, x1, y1, w, color, alpha=1.0):
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(length / max(1.0, w * 0.4)))
        for i in range(steps + 1):
            t = i / steps
            self.circle(int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t),
                        w / 2.0, color, alpha)

    def arc(self, cx, cy, rad, a0, a1, w, color, alpha=1.0):
        steps = max(2, int(abs(a1 - a0) * rad / 3))
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            self.circle(int(cx + rad * math.cos(a)), int(cy + rad * math.sin(a)),
                        w / 2.0, color, alpha)

    def rounded_rect(self, x, y, w, h, r, color, alpha=1.0):
        self.rect(x + r, y, w - 2 * r, h, color, alpha)
        self.rect(x, y + r, w, h - 2 * r, color, alpha)
        for cx, cy in ((x + r, y + r), (x + w - r, y + r),
                       (x + r, y + h - r), (x + w - r, y + h - r)):
            self.circle(cx, cy, r, color, alpha)

    def vgrad(self, top, bot):
        for y in range(self.h):
            t = y / (self.h - 1)
            c = tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(3))
            self.span(y, 0, self.w, c, 1.0)

    def glow(self, cx, cy, r_max, color, a_max, steps=8):
        for i in range(steps, 0, -1):
            f = i / steps
            self.circle(cx, cy, r_max * f, color, a_max * f * f * f)


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", binascii.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path, cv):
    raw = bytearray()
    for y in range(cv.h):
        base = y * cv.w
        row = bytearray(1 + 3 * cv.w)
        row[0] = 0
        row[1::3] = cv.r[base:base + cv.w]
        row[2::3] = cv.g[base:base + cv.w]
        row[3::3] = cv.b[base:base + cv.w]
        raw += row
    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    data = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


# ---------- scene: Lent Light ----------
def draw(cv):
    cv.vgrad(SKY_TOP, SKY_BOT)

    # stars (fixed-seed LCG: deterministic)
    rng = _lcg(11)
    for _ in range(46):
        x = 20 + next(rng) % 980
        y = 20 + next(rng) % 600
        if (x - 205) ** 2 + (y - 175) ** 2 < 130 * 130:
            continue
        r = 1 + next(rng) % 2
        a = 0.35 + (next(rng) % 55) / 100.0
        cv.circle(x, y, r, (255, 244, 214), a)
    # a few 4-point sparkles
    for sx, sy in ((820, 210), (520, 120), (120, 420), (940, 420), (330, 90)):
        cv.rect(sx - 1, sy - 7, 2, 14, GOLD_PALE, 0.7)
        cv.rect(sx - 7, sy - 1, 14, 2, GOLD_PALE, 0.7)
    # shooting star, faint
    cv.thick_line(905, 95, 845, 140, 3, (255, 240, 200), 0.85)
    cv.circle(905, 95, 4, (255, 240, 200), 0.9)

    # moon with soft halo
    cv.glow(205, 175, 240, GOLD_PALE, 0.04, 28)
    cv.circle(205, 175, 76, MOON)

    # hills
    cv.ellipse(300, 1080, 700, 260, HILL_FAR)
    cv.ellipse(800, 1120, 750, 300, HILL_NEAR)
    # ground shadow where the robot stands
    cv.ellipse(670, 845, 110, 14, (10, 13, 26), 0.5)
    # distant fireflies
    for fx, fy in ((150, 690), (880, 620), (940, 780), (90, 790)):
        cv.circle(fx, fy, 12, GOLD, 0.15)
        cv.circle(fx, fy, 4, GOLD, 0.9)

    # wide warm wash from the robot's heart (before the robot)
    cv.glow(660, 640, 330, GOLD, 0.07, 48)

    # ---- robot ----
    # antenna
    cv.thick_line(660, 402, 660, 362, 7, CREAM_SHADE)
    cv.circle(660, 356, 20, GOLD, 0.25)
    cv.circle(660, 356, 11, GOLD)
    # head (feather pass softens the edge, then solid)
    cv.rounded_rect(590, 398, 140, 108, 36, CREAM, 0.18)
    cv.rounded_rect(592, 400, 136, 104, 34, CREAM)
    cv.rounded_rect(592, 470, 136, 34, 20, CREAM_SHADE, 0.35)
    # happy closed eyes (arches) + smile + blush
    cv.arc(628, 452, 13, math.pi, 2 * math.pi, 6, INK)
    cv.arc(692, 452, 13, math.pi, 2 * math.pi, 6, INK)
    cv.arc(660, 470, 16, 0.15 * math.pi, 0.85 * math.pi, 6, INK)
    cv.circle(606, 478, 9, CORAL, 0.55)
    cv.circle(714, 478, 9, CORAL, 0.55)
    # body
    cv.rounded_rect(576, 510, 168, 272, 42, CREAM, 0.18)
    cv.rounded_rect(578, 512, 164, 268, 40, CREAM)
    cv.rounded_rect(600, 540, 120, 150, 24, PANEL)
    cv.rounded_rect(578, 730, 164, 50, 24, CREAM_SHADE, 0.4)
    # arms: left reaches toward the firefly, right rests at its side
    cv.thick_line(592, 566, 486, 606, 20, CREAM)
    cv.circle(480, 608, 14, CREAM)
    cv.thick_line(748, 566, 770, 690, 20, CREAM)
    cv.circle(772, 696, 14, CREAM)
    # legs and feet
    cv.rounded_rect(596, 780, 52, 44, 14, CREAM_SHADE)
    cv.rounded_rect(692, 780, 52, 44, 14, CREAM_SHADE)
    cv.rounded_rect(588, 812, 68, 26, 12, CREAM_DARK)
    cv.rounded_rect(684, 812, 68, 26, 12, CREAM_DARK)
    # glowing heart on the chest
    cv.circle(642, 615, 24, GOLD_DEEP)
    cv.circle(678, 615, 24, GOLD_DEEP)
    cv.polygon([(620, 622), (700, 622), (660, 682)], GOLD_DEEP)
    cv.circle(648, 620, 13, GOLD_PALE)
    cv.circle(672, 620, 13, GOLD_PALE)
    cv.polygon([(638, 626), (682, 626), (660, 664)], GOLD_PALE)
    # bright core of the heart-light spilling over the chest
    cv.glow(660, 640, 150, GOLD, 0.07, 20)

    # ---- tired firefly + its dotted flight trail ----
    x0, y0, cx, cy, x1, y1 = 80, 720, 220, 640, 430, 600
    for i in range(19):
        t = i / 18.0
        px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1
        py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1
        cv.circle(int(px), int(py), 3, GOLD, 0.12 + 0.30 * t)
    # the robot's light reaches the firefly: soft wash around it
    cv.circle(440, 590, 64, GOLD, 0.10)
    # wings (soft round translucent), dark body, head, dim lamp
    cv.circle(430, 558, 12, WING, 0.5)
    cv.circle(458, 556, 12, WING, 0.5)
    cv.ellipse(440, 592, 16, 22, INK)
    cv.circle(454, 574, 9, INK)
    cv.circle(426, 610, 26, GOLD, 0.12)
    cv.circle(426, 610, 11, GOLD_PALE)

    # grass tufts along the hill line
    for gx in (120, 250, 350, 520, 700, 780, 830, 930):
        cv.polygon([(gx, 905), (gx + 7, 876), (gx + 14, 905)], GRASS)
    # three tiny glowing flowers in the foreground
    for fx, fy in ((180, 930), (300, 950), (880, 940)):
        cv.thick_line(fx, fy, fx, fy - 26, 3, GRASS)
        cv.circle(fx, fy - 32, 10, GOLD, 0.20)
        cv.circle(fx, fy - 32, 6, GOLD_PALE)


def main():
    out = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out, exist_ok=True)
    cv = Canvas(W, H)
    draw(cv)
    path = os.path.join(out, "entry.png")
    size = write_png(path, cv)
    print(f"wrote {path} {size} bytes 1024x1024")


if __name__ == "__main__":
    main()
