"""Eye Within Words — a Python + pygame piece, browser-ready via pygbag.

Rows of drifting text. Inside an almond-shaped eyelid they flare bright;
an iris made of concentric rings of rotating text and a dark pupil sit on top.
A blink controller closes and reopens the lids.

Controls
    SPACE / click / tap  blink          B  toggle auto-blink
    Z  toggle auto-zoom                 C  next palette
    R  reseed (new text layout)         H  toggle help
    ESC  quit (desktop)

Run locally:   python main.py
Web build:     see deploy.sh  (pygbag -> static folder -> Vercel)
"""

import asyncio
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
WIDTH, HEIGHT = 1280, 720
FPS = 60
IS_WEB = sys.platform == "emscripten"   # pygbag / WebAssembly build
CX, CY = WIDTH // 2, HEIGHT // 2

ROW_H = 15            # text row pitch
ROW_FONT = 17
RING_FONT = 15
LID_FONT = 16

EYE_A = 430           # half width of the eye
EYE_B_UP = 205        # upper lid max height
EYE_B_LOW = 140       # lower lid max height
LID_POWER = 0.85      # lid curve shape

IRIS_R = 128
PUPIL_R = 44

LINES = [
    "every pattern is a sentence the world forgot to finish",
    "look closely and the dark begins to read back",
    "a thought leaves a trace before it leaves the mind",
    "the quiet between two words is also language",
    "nothing is ever truly hidden only unattended",
    "attention is the lens and the light at once",
    "we are made of the things we keep noticing",
    "somewhere inside the noise there is a shape looking out",
    "the screen is a window that learned to stare",
    "meaning blooms where the eye refuses to rush",
    "every line of code is a small decision to be seen",
    "stay long enough and the static starts to breathe",
    "what you watch closely begins to watch you",
    "patience is a kind of light",
    "the details are where the universe keeps its secrets",
    "a single glance can hold a whole night sky",
    "listen to the geometry of things",
    "silence has its own typography",
    "the world is written in patterns waiting to be read",
    "perception is the brushstroke that paints the real",
    "to truly see is to be quietly changed",
    "even darkness carries a kind of meaning",
    "depth is only surface that kept going",
    "curiosity is the first form of light",
    "all things are woven from the same thread of thought",
    "wonder opens like an eye in an unlit room",
]

SHORT_WORDS = sorted({w for line in LINES for w in line.split() if 3 <= len(w) <= 7})


@dataclass(frozen=True)
class Palette:
    name: str
    bg_top: Tuple[int, int, int]
    bg_bottom: Tuple[int, int, int]
    row_dim: Tuple[int, int, int]
    row_bright: Tuple[int, int, int]
    iris: Tuple[Tuple[int, int, int], ...]   # inner -> outer


PALETTES = [
    Palette("midnight", (16, 8, 72), (1, 1, 10), (120, 140, 195), (236, 242, 255),
            ((90, 235, 225), (70, 200, 238), (80, 160, 245), (115, 125, 245), (160, 115, 238))),
    Palette("ember", (52, 10, 24), (6, 1, 3), (190, 130, 120), (255, 238, 215),
            ((255, 222, 140), (255, 180, 95), (244, 128, 82), (206, 86, 102), (156, 64, 124))),
    Palette("violet", (36, 8, 84), (3, 1, 12), (150, 120, 200), (246, 238, 255),
            ((255, 190, 255), (226, 150, 255), (176, 124, 255), (124, 138, 255), (96, 178, 255))),
    Palette("mono", (14, 14, 20), (1, 1, 2), (130, 134, 150), (250, 250, 252),
            ((255, 255, 255), (225, 228, 235), (190, 195, 208), (155, 162, 180), (120, 128, 150))),
]


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def scale_color(c, s):
    return tuple(int(clamp(v * s, 0, 255)) for v in c)


# ----------------------------------------------------------------------------
# Blink controller
# ----------------------------------------------------------------------------
class BlinkController:
    """Returns lid openness in [0, 1]; 1 = fully open, 0 = closed."""

    CLOSE = 0.085
    HOLD = 0.05
    OPEN = 0.18

    def __init__(self, rng: random.Random, auto_blink: bool = True) -> None:
        self.rng = rng
        self.auto_blink = auto_blink
        self.t0: Optional[float] = None
        self.double_pending = False
        self.next_auto = 2.2

    @property
    def total(self) -> float:
        return self.CLOSE + self.HOLD + self.OPEN

    def trigger_blink(self, now: float, allow_double: bool = True) -> None:
        if self.t0 is not None:
            return
        self.t0 = now
        self.double_pending = allow_double and self.rng.random() < 0.2

    def update(self, now: float) -> float:
        if self.auto_blink and self.t0 is None and now >= self.next_auto:
            self.trigger_blink(now)
        if self.t0 is None:
            return 1.0

        t = now - self.t0
        if t < self.CLOSE:
            k = t / self.CLOSE
            return 1.0 - k * k                      # ease-in: lids slam shut
        if t < self.CLOSE + self.HOLD:
            return 0.0
        if t < self.total:
            k = (t - self.CLOSE - self.HOLD) / self.OPEN
            return 1.0 - (1.0 - k) * (1.0 - k)      # ease-out: lids glide open

        # blink finished
        if self.double_pending:
            self.double_pending = False
            self.t0 = now
            return 0.0
        self.t0 = None
        self.next_auto = now + self.rng.uniform(2.6, 6.2)
        return 1.0


# ----------------------------------------------------------------------------
# Camera (slow breathing zoom on the eye)
# ----------------------------------------------------------------------------
class Camera:
    def __init__(self) -> None:
        self.auto_zoom = True
        self.zoom = 1.0

    def update(self, now: float, dt: float, override: Optional[float] = None) -> float:
        if override is not None:
            target = override
        elif self.auto_zoom:
            target = 1.0 + 0.09 * (0.5 + 0.5 * math.sin(now * 0.33))
        else:
            target = 1.0
        self.zoom += (target - self.zoom) * min(1.0, dt * 4.0)
        return self.zoom


# ----------------------------------------------------------------------------
# Row strip (one scrolling line of text)
# ----------------------------------------------------------------------------
class RowStrip:
    __slots__ = ("dim", "bright", "width", "speed", "offset")

    def __init__(self, dim: pygame.Surface, bright: pygame.Surface, speed: float, offset: float):
        self.dim = dim
        self.bright = bright
        self.width = dim.get_width()
        self.speed = speed
        self.offset = offset


# ----------------------------------------------------------------------------
# App
# ----------------------------------------------------------------------------
class EyeWithinWordsApp:
    def __init__(self, test_frames: int = 0, screenshot_dir: Optional[str] = None) -> None:
        pygame.init()
        pygame.display.set_caption("Eye Within Words")
        try:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.RESIZABLE)
        except pygame.error:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))

        self.test_frames = test_frames
        self.screenshot_dir = screenshot_dir
        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)

        self.row_font = pygame.font.Font(None, ROW_FONT)
        self.ring_font = pygame.font.Font(None, RING_FONT)
        self.lid_font = pygame.font.Font(None, LID_FONT)
        self.lid_font.set_bold(True)
        self.ui_font = pygame.font.Font(None, 24)

        self.seed = 20260 if test_frames else random.randint(10000, 999999)
        self.palette_idx = 0
        self.show_help = test_frames == 0
        # seconds after start to auto-hide help once; None after it fires so H can re-show it
        self.help_until: Optional[float] = 6.0

        self.rng = random.Random(self.seed)
        self.blink_ctrl = BlinkController(self.rng, auto_blink=test_frames == 0)
        self.camera = Camera()
        self.override_zoom: Optional[float] = None

        self.gaze = [0.0, 0.0]
        self.last_mouse = (-1, -1)
        self.last_mouse_move = -99.0
        self.ring_angles: List[float] = []

        self.eye_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.mask_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        self._build_all_layers()

    # ------------------------------------------------------------------ build
    @property
    def palette(self) -> Palette:
        return PALETTES[self.palette_idx]

    def _build_all_layers(self) -> None:
        rng = random.Random(self.seed)
        pal = self.palette
        self._build_background(pal)
        self._build_rows(rng, pal)
        self._build_iris(rng, pal)
        self._build_pupil()
        self._build_lid_words(rng, pal)
        self._build_vignette()
        self.ring_angles = [rng.uniform(0, 360) for _ in self.rings]

    def _build_background(self, pal: Palette) -> None:
        bg = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            t = (y / HEIGHT) ** 0.8
            pygame.draw.line(bg, lerp_color(pal.bg_top, pal.bg_bottom, t), (0, y), (WIDTH, y))
        self.bg = bg.convert()

    def _row_text(self, rng: random.Random, min_width: int) -> str:
        parts: List[str] = []
        order = LINES[:]
        rng.shuffle(order)
        i = 0
        while True:
            parts.append(order[i % len(order)])
            text = "    ".join(parts) + "    "
            if self.row_font.size(text)[0] >= min_width:
                return text
            i += 1

    def _build_rows(self, rng: random.Random, pal: Palette) -> None:
        self.rows: List[RowStrip] = []
        n = HEIGHT // ROW_H + 2
        for i in range(n):
            y_mid = i * ROW_H + ROW_H / 2
            dist = abs(y_mid - CY) / (HEIGHT / 2)
            text = self._row_text(rng, WIDTH + 120)
            dim_s = clamp(0.10 + 0.20 * rng.random() + 0.10 * (1 - dist), 0.08, 0.5)
            bright_s = clamp(0.80 + 0.2 * rng.random(), 0, 1)
            dim = self.row_font.render(text, True, scale_color(pal.row_dim, dim_s)).convert_alpha()
            bright = self.row_font.render(text, True, scale_color(pal.row_bright, bright_s)).convert_alpha()
            speed = (14 + 40 * rng.random()) * (1 if i % 2 == 0 else -1)
            self.rows.append(RowStrip(dim, bright, speed, rng.uniform(0, dim.get_width())))

    def _build_iris(self, rng: random.Random, pal: Palette) -> None:
        # dark disc behind the rings so bright row text does not bleed through
        size = IRIS_R * 2 + 40
        disc = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        for i in range(18, -1, -1):
            a = int(236 * (1 - i / 19))
            pygame.draw.circle(disc, (3, 8, 22, a), (c, c), IRIS_R + i)
        pygame.draw.circle(disc, (3, 8, 22, 236), (c, c), IRIS_R)
        self.iris_disc = disc.convert_alpha()

        self.rings: List[Tuple[pygame.Surface, float]] = []
        radii = list(range(PUPIL_R + 14, IRIS_R, 11))
        n = len(radii)
        for idx, r in enumerate(radii):
            t = idx / max(1, n - 1)
            pos = t * (len(pal.iris) - 1)
            lo = int(pos)
            hi = min(len(pal.iris) - 1, lo + 1)
            base = lerp_color(pal.iris[lo], pal.iris[hi], pos - lo)
            surf = self._build_ring(rng, r, base)
            speed = (6 + 9 * rng.random()) * (1 if idx % 2 == 0 else -1)
            self.rings.append((surf, speed))

    def _build_ring(self, rng: random.Random, radius: int, color) -> pygame.Surface:
        size = int(2 * (radius + 14))
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size / 2
        circumference = 2 * math.pi * radius

        chars: List[str] = []
        advances: List[float] = []
        total = 0.0
        pool = LINES[:]
        rng.shuffle(pool)
        k = 0
        while total < circumference:
            for ch in pool[k % len(pool)] + "  ":
                adv = self.ring_font.size(ch)[0]
                if total + adv > circumference:
                    total = circumference + 1
                    break
                chars.append(ch)
                advances.append(adv)
                total += adv
            k += 1
        used = sum(advances) or 1.0
        stretch = circumference / used

        x = 0.0
        for ch, adv in zip(chars, advances):
            if ch != " ":
                theta = ((x + adv / 2) * stretch) / radius - math.pi / 2
                shade = rng.uniform(0.72, 1.0)
                glyph = self.ring_font.render(ch, True, scale_color(color, shade))
                glyph = pygame.transform.rotate(glyph, -(math.degrees(theta) + 90))
                px = c + radius * math.cos(theta)
                py = c + radius * math.sin(theta)
                surf.blit(glyph, glyph.get_rect(center=(px, py)))
            x += adv
        return surf.convert_alpha()

    def _build_pupil(self) -> None:
        halo = 24
        size = (PUPIL_R + halo) * 2
        c = size // 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        for i in range(halo, 0, -1):
            a = int(170 * (1 - i / halo) ** 1.4)
            pygame.draw.circle(surf, (0, 2, 10, a), (c, c), PUPIL_R + i)
        pygame.draw.circle(surf, (0, 0, 0, 255), (c, c), PUPIL_R)
        self.pupil = surf.convert_alpha()

    def _build_lid_words(self, rng: random.Random, pal: Palette) -> None:
        self.lid_words: List[Tuple[pygame.Surface, float, bool]] = []
        count = 15
        for up in (True, False):
            for i in range(count):
                u = lerp(-0.90, 0.90, (i + 0.5) / count) + rng.uniform(-0.01, 0.01)
                word = rng.choice(SHORT_WORDS)
                surf = self.lid_font.render(word, True, pal.row_bright).convert_alpha()
                self.lid_words.append((surf, u, up))

    def _build_vignette(self) -> None:
        v = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        v.fill((0, 0, 0, 170))
        steps = 36
        for i in range(steps):
            t = i / (steps - 1)
            a = int(170 * (1 - t) ** 1.6)
            w = int(lerp(WIDTH * 2.0, WIDTH * 0.35, t))
            h = int(lerp(HEIGHT * 2.0, HEIGHT * 0.30, t))
            pygame.draw.ellipse(v, (0, 0, 0, a), (CX - w // 2, CY - h // 2, w, h))
        self.vignette = v.convert_alpha()

    # --------------------------------------------------------------- geometry
    def lid_dy(self, x: float, openness: float, up: bool, zoom: float) -> float:
        """Vertical offset from eye centre of the lid edge at horizontal offset x."""
        a = EYE_A * zoom
        u = abs(x) / a
        if u >= 1.0:
            return 0.0
        shape = (1.0 - u * u) ** LID_POWER
        b = (EYE_B_UP if up else EYE_B_LOW) * zoom * openness
        return -b * shape if up else b * shape

    def eye_half_width_at(self, dy: float, openness: float, zoom: float) -> float:
        """Half-width of the open eye at vertical offset dy from centre (0 if outside)."""
        up = dy < 0
        b = (EYE_B_UP if up else EYE_B_LOW) * zoom * openness
        if b < 1.0:
            return 0.0
        r = abs(dy) / b
        if r >= 1.0:
            return 0.0
        return EYE_A * zoom * math.sqrt(max(0.0, 1.0 - r ** (1.0 / LID_POWER)))

    # ----------------------------------------------------------------- update
    def update(self, now: float, dt: float) -> Tuple[float, float]:
        openness = self.blink_ctrl.update(now)
        zoom = self.camera.update(now, dt, self.override_zoom)

        for row in self.rows:
            row.offset = (row.offset + row.speed * dt) % row.width
        for i, (_, speed) in enumerate(self.rings):
            self.ring_angles[i] = (self.ring_angles[i] + speed * dt) % 360

        mouse = pygame.mouse.get_pos()
        if mouse != self.last_mouse:
            if self.last_mouse != (-1, -1):
                self.last_mouse_move = now
            self.last_mouse = mouse
        if now - self.last_mouse_move < 3.0:
            tx, ty = (mouse[0] - CX) * 0.09, (mouse[1] - CY) * 0.07
        else:
            tx = math.sin(now * 0.40) * 34 + math.sin(now * 0.93) * 10
            ty = math.sin(now * 0.31 + 1.0) * 12
        tx, ty = clamp(tx, -52, 52), clamp(ty, -22, 22)
        k = min(1.0, dt * 5.0)
        self.gaze[0] += (tx - self.gaze[0]) * k
        self.gaze[1] += (ty - self.gaze[1]) * k
        return openness, zoom

    # ------------------------------------------------------------------- draw
    def draw(self, now: float, openness: float, zoom: float) -> None:
        s = self.screen
        s.blit(self.bg, (0, 0))

        # 1. dim background rows (full width)
        for i, row in enumerate(self.rows):
            y = i * ROW_H
            x = -row.offset
            s.blit(row.dim, (x, y))
            s.blit(row.dim, (x + row.width, y))

        # 2. bright rows, clipped to the open eye
        if openness > 0.01:
            for i, row in enumerate(self.rows):
                y = i * ROW_H
                half = self.eye_half_width_at(y + ROW_H / 2 - CY, openness, zoom)
                if half < 2:
                    continue
                s.set_clip(pygame.Rect(int(CX - half), y, int(half * 2), ROW_H))
                x = -row.offset
                s.blit(row.bright, (x, y))
                s.blit(row.bright, (x + row.width, y))
            s.set_clip(None)

            self._draw_iris(openness, zoom)

        # 3. lid outline made of words
        self._draw_lids(openness, zoom)

        # 4. vignette + UI
        s.blit(self.vignette, (0, 0))
        self._draw_ui(now)

    def _eye_rect(self, zoom: float) -> pygame.Rect:
        w = int(EYE_A * zoom * 2 + 40)
        h = int((EYE_B_UP + EYE_B_LOW) * zoom + 60)
        r = pygame.Rect(0, 0, min(w, WIDTH), min(h, HEIGHT))
        r.center = (CX, CY + int((EYE_B_LOW - EYE_B_UP) * zoom / 2))
        return r.clip(pygame.Rect(0, 0, WIDTH, HEIGHT))

    def _draw_iris(self, openness: float, zoom: float) -> None:
        rect = self._eye_rect(zoom)
        layer = self.eye_layer.subsurface(rect)
        mask = self.mask_layer.subsurface(rect)
        layer.fill((0, 0, 0, 0))
        mask.fill((0, 0, 0, 0))

        # eye-shaped mask
        n = 56
        upper, lower = [], []
        for i in range(n + 1):
            x = lerp(-EYE_A * zoom, EYE_A * zoom, i / n)
            upper.append((CX + x - rect.x, CY + self.lid_dy(x, openness, True, zoom) - rect.y))
            lower.append((CX + x - rect.x, CY + self.lid_dy(x, openness, False, zoom) - rect.y))
        pygame.draw.polygon(mask, (255, 255, 255, 255), upper + lower[::-1])

        # iris stack
        ix = CX + self.gaze[0] - rect.x
        iy = CY + self.gaze[1] - rect.y
        disc = pygame.transform.rotozoom(self.iris_disc, 0, zoom) if abs(zoom - 1) > 0.005 else self.iris_disc
        layer.blit(disc, disc.get_rect(center=(ix, iy)))
        for i, (surf, _) in enumerate(self.rings):
            rot = pygame.transform.rotozoom(surf, self.ring_angles[i], zoom)
            layer.blit(rot, rot.get_rect(center=(ix, iy)))

        pulse = 1.0 + 0.05 * math.sin(self.ring_angles[0] * 0.05)
        pupil = pygame.transform.rotozoom(self.pupil, 0, zoom * pulse)
        layer.blit(pupil, pupil.get_rect(center=(ix, iy)))

        # tiny glint
        gx, gy = ix - 20 * zoom, iy - 22 * zoom
        pygame.draw.ellipse(layer, (255, 255, 255, 215), (gx - 6 * zoom, gy - 4 * zoom, 12 * zoom, 8 * zoom))

        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(layer, rect.topleft)

    def _draw_lids(self, openness: float, zoom: float) -> None:
        s = self.screen
        n = 56
        for up in (True, False):
            pts = []
            for i in range(n + 1):
                x = lerp(-EYE_A * zoom, EYE_A * zoom, i / n)
                pts.append((CX + x, CY + self.lid_dy(x, openness, up, zoom)))
            pygame.draw.lines(s, scale_color(self.palette.row_bright, 0.55), False, pts, 1)

        for surf, u, up in self.lid_words:
            x = u * EYE_A * zoom
            y = self.lid_dy(x, openness, up, zoom)
            y2 = self.lid_dy(x + 3, openness, up, zoom)
            y1 = self.lid_dy(x - 3, openness, up, zoom)
            angle = math.degrees(math.atan2(-(y2 - y1), 6.0))   # pygame rotates CCW
            rot = pygame.transform.rotate(surf, angle)
            off = -9 if up else 9                               # sit just outside the edge
            s.blit(rot, rot.get_rect(center=(CX + x, CY + y + off)))

    def _draw_ui(self, now: float) -> None:
        if not self.show_help:
            return
        lines = [
            "SPACE / tap  blink      B  auto-blink: %s" % ("on" if self.blink_ctrl.auto_blink else "off"),
            "Z  auto-zoom: %s      C  palette: %s      R  reseed      H  hide" % (
                "on" if self.camera.auto_zoom else "off", self.palette.name),
        ]
        y = HEIGHT - 20 - 26 * len(lines)
        for line in lines:
            img = self.ui_font.render(line, True, (205, 215, 240))
            img.set_alpha(190)
            self.screen.blit(img, (24, y))
            y += 26

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event, now: float) -> bool:
        """Returns False when the app should quit."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.FINGERDOWN:
            self.blink_ctrl.trigger_blink(now, allow_double=False)
        elif event.type == pygame.KEYDOWN:
            k = event.key
            if k == pygame.K_ESCAPE:
                # quitting in the browser would leave a frozen canvas, so ESC is desktop-only
                if not IS_WEB:
                    return False
            elif k == pygame.K_SPACE:
                self.blink_ctrl.trigger_blink(now, allow_double=False)
            elif k == pygame.K_b:
                self.blink_ctrl.auto_blink = not self.blink_ctrl.auto_blink
            elif k == pygame.K_z:
                self.camera.auto_zoom = not self.camera.auto_zoom
            elif k == pygame.K_c:
                self.palette_idx = (self.palette_idx + 1) % len(PALETTES)
                self._build_all_layers()
            elif k == pygame.K_r:
                self.seed = random.randint(10000, 999999)
                self._build_all_layers()
            elif k == pygame.K_h:
                self.show_help = not self.show_help
        return True

    # -------------------------------------------------------------------- run
    async def run(self) -> None:
        clock = pygame.time.Clock()
        running = True
        frame_idx = 0
        prev_time = start_time = time.perf_counter()
        test_dt = 1.0 / 30.0

        while running:
            if self.test_frames:
                now, dt = frame_idx * test_dt, test_dt
                if frame_idx == 40:
                    self.blink_ctrl.trigger_blink(now, allow_double=False)
            else:
                now = time.perf_counter()
                dt = min(0.05, max(0.001, now - prev_time))
                prev_time = now

            for event in pygame.event.get():
                if not self.handle_event(event, now):
                    running = False

            # auto-hide help once, by wall time (was per-frame, which re-hid it after every H press)
            if self.help_until is not None and not self.test_frames and now - start_time > self.help_until:
                self.show_help = False
                self.help_until = None

            openness, zoom = self.update(now, dt)
            self.draw(now, openness, zoom)
            pygame.display.flip()

            if self.test_frames:
                if self.screenshot_dir and frame_idx in (20, 41, 42, 43, 60):
                    path = os.path.join(self.screenshot_dir, "frame_%03d.png" % frame_idx)
                    pygame.image.save(self.screen, path)
                    print("saved", path, "openness=%.2f" % openness)
                frame_idx += 1
                if frame_idx >= self.test_frames:
                    running = False
            else:
                frame_idx += 1
                clock.tick(FPS)

            await asyncio.sleep(0)     # required by pygbag: yield to the browser

        pygame.quit()


async def main() -> None:
    test_frames = 0
    shot_dir: Optional[str] = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--test-frames" and i + 1 < len(args):
            test_frames = int(args[i + 1])
        elif a == "--screenshot-dir" and i + 1 < len(args):
            shot_dir = args[i + 1]
    app = EyeWithinWordsApp(test_frames=test_frames, screenshot_dir=shot_dir)
    await app.run()


asyncio.run(main())
