"""
Insects_gui.py — simulador interativo da atração de insetos por luz.

Tela inicial:
    - Sliders para pheromone, friction, base accel, bias strength,
      número de machos azuis (0-200), fêmeas azuis (0-8),
      max generations e ângulo de preferência dos azuis.
    - Botão INICIAR, PADRÃO (restaura defaults) e SAIR.

Tela de simulação:
    - Visualização em tempo real dos agentes.
    - Estatísticas na lateral: geração, cópulas, contagens por cor.
    - Controles: P=pausa, R=voltar ao setup, Espaço=velocidade x10, ESC=sair.
"""

import sys
import math
import random
import pygame
from pygame.math import Vector2


# ============================================================
# CONSTANTES
# ============================================================

WINDOW_W = 1250
WINDOW_H = 800

SIM_W = 800
SIM_H = 800

PANEL_X = SIM_W + 20
PANEL_W = WINDOW_W - SIM_W - 40

FPS = 60

# Defaults (batem com o batch)
DEFAULT_PHEROMONE = 0.65
DEFAULT_FRICTION = 0.97
DEFAULT_BASE_ACCEL = 0.21
DEFAULT_BIAS_STRENGTH = 0.05

TOTAL_MALES = 200
TOTAL_FEMALES = 8
COPULATIONS_PER_GEN = 50
OFFSPRING_PER_COPULATION = 4
MAX_GENERATIONS_DEFAULT = 1600

MALE_RADIUS = 4
FEMALE_RADIUS = 7
TRAIL_LENGTH = 310
TRAIL_HALF_ANGLE = math.radians(10)

# Cores
C_BG = (15, 15, 20)
C_PANEL = (30, 30, 40)
C_PANEL_LIGHT = (55, 55, 70)
C_TEXT = (230, 230, 230)
C_TEXT_DIM = (150, 150, 165)
C_ACCENT = (90, 170, 220)
C_BLUE_MALE = (120, 170, 255)
C_RED_MALE = (255, 130, 130)
C_BLUE_FEMALE = (60, 100, 220)
C_RED_FEMALE = (220, 60, 60)
C_TRAIL_BLUE = (80, 130, 240, 60)
C_TRAIL_RED = (230, 80, 80, 60)
C_SUCCESS = (120, 220, 120)
C_WARN = (240, 200, 90)


# ============================================================
# UI
# ============================================================

class Slider:
    def __init__(self, x, y, w, label, min_v, max_v, value,
                 fmt="{:.3f}", step=None, unit=""):
        self.x = x
        self.y = y
        self.w = w
        self.label = label
        self.min_v = min_v
        self.max_v = max_v
        self.value = value
        self.fmt = fmt
        self.step = step
        self.unit = unit
        self.dragging = False
        self.h = 8
        self.knob_r = 9
        self.track_rect = pygame.Rect(x, y + 22, w, self.h)

    def _knob_x(self):
        t = (self.value - self.min_v) / (self.max_v - self.min_v)
        return self.track_rect.x + t * self.track_rect.w

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            kx = self._knob_x()
            if (abs(mx - kx) <= self.knob_r + 4 and
                    abs(my - self.track_rect.centery) <= self.knob_r + 4):
                self.dragging = True
                return True
            if self.track_rect.collidepoint(mx, my):
                self.dragging = True
                self._set_from_x(mx)
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False
                return True
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from_x(event.pos[0])
            return True
        return False

    def _set_from_x(self, mx):
        t = (mx - self.track_rect.x) / self.track_rect.w
        t = max(0.0, min(1.0, t))
        v = self.min_v + t * (self.max_v - self.min_v)
        if self.step:
            v = round(v / self.step) * self.step
        self.value = v

    def draw(self, screen, font, font_small):
        label_surf = font.render(self.label, True, C_TEXT)
        screen.blit(label_surf, (self.x, self.y - 2))
        val_str = self.fmt.format(self.value) + ((" " + self.unit) if self.unit else "")
        val_surf = font_small.render(val_str, True, C_ACCENT)
        screen.blit(val_surf, (self.x + self.w - val_surf.get_width(), self.y))
        pygame.draw.rect(screen, C_PANEL_LIGHT, self.track_rect, border_radius=4)
        kx = int(self._knob_x())
        fill = pygame.Rect(self.track_rect.x, self.track_rect.y,
                           kx - self.track_rect.x, self.track_rect.h)
        pygame.draw.rect(screen, C_ACCENT, fill, border_radius=4)
        pygame.draw.circle(screen, C_TEXT, (kx, self.track_rect.centery), self.knob_r)
        pygame.draw.circle(screen, C_ACCENT, (kx, self.track_rect.centery),
                           self.knob_r - 3)


class Button:
    def __init__(self, x, y, w, h, label, action=None, color=C_ACCENT):
        self.rect = pygame.Rect(x, y, w, h)
        self.label = label
        self.action = action
        self.color = color
        self.hovered = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.action:
                    self.action()
                return True
        return False

    def draw(self, screen, font):
        base = self.color if not self.hovered else tuple(min(255, c + 30) for c in self.color)
        pygame.draw.rect(screen, base, self.rect, border_radius=6)
        pygame.draw.rect(screen, C_TEXT, self.rect, 2, border_radius=6)
        s = font.render(self.label, True, C_TEXT)
        screen.blit(s, (self.rect.x + (self.rect.w - s.get_width()) // 2,
                        self.rect.y + (self.rect.h - s.get_height()) // 2))


# ============================================================
# MODELO
# ============================================================

def point_in_triangle(p, a, b, c):
    def sign(p1, p2, p3):
        return (p1.x - p3.x) * (p2.y - p3.y) - (p2.x - p3.x) * (p1.y - p3.y)
    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def binomial_random(n, p):
    if n <= 0 or p <= 0:
        return 0
    if p >= 1:
        return n
    return sum(1 for _ in range(n) if random.random() < p)


class Male:
    __slots__ = ("pos", "vel", "is_biased")
    def __init__(self, pos, vel, is_biased):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.is_biased = is_biased


class Female:
    __slots__ = ("pos", "vel", "is_biased", "copulated_with")
    def __init__(self, pos, vel, is_biased):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.is_biased = is_biased
        self.copulated_with = []


class Simulation:
    def __init__(self, params):
        self.params = params
        self.trail_surf = pygame.Surface((SIM_W, SIM_H), pygame.SRCALPHA)
        self.reset()

    def reset(self):
        p = self.params
        self.generation = 0
        self.copulation_count = 0
        self.n1 = self.n2 = self.n3 = self.n4 = 0
        self.finished = False
        self.winner = None
        self.finished_generation = None

        self.blue_pref_angle = math.radians(p["blue_pref_deg"])

        n_blue_m = int(p["blue_males"])
        n_red_m = TOTAL_MALES - n_blue_m
        n_blue_f = int(p["blue_females"])
        n_red_f = TOTAL_FEMALES - n_blue_f

        pref = Vector2(math.cos(self.blue_pref_angle),
                       math.sin(self.blue_pref_angle))

        self.males = []
        for _ in range(n_blue_m):
            self.males.append(Male(
                (random.uniform(0, SIM_W), random.uniform(0, SIM_H)),
                pref * 2, True))
        for _ in range(n_red_m):
            a = random.uniform(0, 2 * math.pi)
            self.males.append(Male(
                (random.uniform(0, SIM_W), random.uniform(0, SIM_H)),
                (math.cos(a), math.sin(a)) * 2, False))

        self.females = []
        for _ in range(n_blue_f):
            self.females.append(Female(
                (random.uniform(0, SIM_W), random.uniform(0, SIM_H)),
                pref * 2, True))
        for _ in range(n_red_f):
            a = random.uniform(0, 2 * math.pi)
            self.females.append(Female(
                (random.uniform(0, SIM_W), random.uniform(0, SIM_H)),
                (math.cos(a), math.sin(a)) * 2, False))

    def _female_update(self, f):
        f.pos += f.vel
        f.pos.x %= SIM_W
        f.pos.y %= SIM_H

    def _male_update(self, male):
        p = self.params
        acc = Vector2(0, 0)
        in_trail = False
        for f in self.females:
            if f.contains_point(male.pos):
                in_trail = True
                d = f.pos - male.pos
                if d.length() > 0:
                    acc += d.normalize() * p["pheromone"]
                break
        if not in_trail:
            if male.vel.length() > 0:
                acc += male.vel.normalize() * p["base_accel"]
            if male.is_biased:
                pref = Vector2(math.cos(self.blue_pref_angle),
                               math.sin(self.blue_pref_angle))
                cur = male.vel.normalize() if male.vel.length() > 0 else Vector2(1, 0)
                acc += (pref - cur) * p["bias_strength"]
        male.vel += acc
        male.vel *= p["friction"]
        male.pos += male.vel
        male.pos.x %= SIM_W
        male.pos.y %= SIM_H

    def step(self):
        if self.finished:
            return
        for f in self.females:
            self._female_update(f)
        for male in self.males:
            self._male_update(male)
            for female in self.females:
                if (male.pos - female.pos).length() < (MALE_RADIUS + FEMALE_RADIUS):
                    if male not in female.copulated_with:
                        if male.is_biased and female.is_biased:
                            self.n1 += 1
                        elif not male.is_biased and not female.is_biased:
                            self.n2 += 1
                        elif male.is_biased and not female.is_biased:
                            self.n3 += 1
                        else:
                            self.n4 += 1
                        self.copulation_count += 1
                        female.copulated_with.append(male)
                        male.pos = Vector2(random.uniform(0, SIM_W),
                                           random.uniform(0, SIM_H))
                        a = random.uniform(0, 2 * math.pi)
                        male.vel = Vector2(math.cos(a), math.sin(a)) * 2
                        break
        if self.copulation_count >= COPULATIONS_PER_GEN:
            self._next_generation()

    def _next_generation(self):
        blue_from_pure = self.n1 * OFFSPRING_PER_COPULATION
        red_from_pure = self.n2 * OFFSPRING_PER_COPULATION
        total_mixed = self.n3 + self.n4
        total_offspring_mixed = total_mixed * OFFSPRING_PER_COPULATION
        mixed_blue = (binomial_random(total_offspring_mixed, 0.5)
                      if total_offspring_mixed > 0 else 0)
        mixed_red = total_offspring_mixed - mixed_blue
        new_biased = blue_from_pure + mixed_blue
        new_unbiased = red_from_pure + mixed_red
        self.generation += 1

        if new_biased <= 0:
            self.finished = True
            self.winner = "vermelho"
            self.finished_generation = self.generation
            return
        if new_unbiased <= 0:
            self.finished = True
            self.winner = "azul"
            self.finished_generation = self.generation
            return

        total = new_biased + new_unbiased
        p_blue_f = new_biased / total
        n_blue_f = binomial_random(TOTAL_FEMALES, p_blue_f)
        n_red_f = TOTAL_FEMALES - n_blue_f

        self.blue_pref_angle = random.uniform(0, 2 * math.pi)
        pref = Vector2(math.cos(self.blue_pref_angle),
                       math.sin(self.blue_pref_angle))

        self.males = []
        for _ in range(new_biased):
            self.males.append(Male(
                (random.uniform(0, SIM_W), random.uniform(0, SIM_H)),
                pref * 2, True))
        for _ in range(new_unbiased):
            a = random.uniform(0, 2 * math.pi)
            self.males.append(Male(
                (random.uniform(0, SIM_W), random.uniform(0, SIM_H)),
                (math.cos(a), math.sin(a)) * 2, False))

        self.females = []
        for _ in range(n_blue_f):
            self.females.append(Female(
                (random.uniform(0, SIM_W), random.uniform(0, SIM_H)),
                pref * 2, True))
        for _ in range(n_red_f):
            a = random.uniform(0, 2 * math.pi)
            self.females.append(Female(
                (random.uniform(0, SIM_W), random.uniform(0, SIM_H)),
                (math.cos(a), math.sin(a)) * 2, False))

        self.copulation_count = 0
        self.n1 = self.n2 = self.n3 = self.n4 = 0

        if self.generation >= self.params["max_generations"]:
            self.finished = True
            self.winner = "inconclusivo"
            self.finished_generation = self.generation


# Adiciona o método contains_point à Female (depois da definição)
def _female_contains(self, point):
    vlen = self.vel.length()
    if vlen == 0:
        return False
    direction = self.vel / vlen
    base = self.pos - direction * TRAIL_LENGTH
    perp = Vector2(-direction.y, direction.x)
    half = TRAIL_LENGTH * math.tan(TRAIL_HALF_ANGLE)
    a = self.pos
    b = base + perp * half
    c = base - perp * half
    return point_in_triangle(point, a, b, c)

Female.contains_point = _female_contains


# ============================================================
# APP
# ============================================================

class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Insetos — Simulador Interativo")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 16, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 13)
        self.font_big = pygame.font.SysFont("consolas", 22, bold=True)
        self.font_huge = pygame.font.SysFont("consolas", 28, bold=True)

        self.state = "setup"
        self.sim = None
        self.paused = False
        self.speed_multiplier = 1

        self._build_setup_ui()

    def _build_setup_ui(self):
        self.params = {
            "pheromone": DEFAULT_PHEROMONE,
            "friction": DEFAULT_FRICTION,
            "base_accel": DEFAULT_BASE_ACCEL,
            "bias_strength": DEFAULT_BIAS_STRENGTH,
            "blue_males": 100,
            "blue_females": 4,
            "max_generations": MAX_GENERATIONS_DEFAULT,
            "blue_pref_deg": 0.0,
        }

        x0, w, y, gap = 60, 500, 110, 62
        self.sliders = [
            Slider(x0, y + gap * 0, w, "Pheromone acceleration",
                   0.0, 1.5, self.params["pheromone"], "{:.3f}"),
            Slider(x0, y + gap * 1, w, "Friction (slipperiness)",
                   0.85, 0.999, self.params["friction"], "{:.4f}"),
            Slider(x0, y + gap * 2, w, "Base acceleration",
                   0.0, 0.6, self.params["base_accel"], "{:.3f}"),
            Slider(x0, y + gap * 3, w, "Bias strength",
                   0.0, 0.2, self.params["bias_strength"], "{:.3f}"),
            Slider(x0, y + gap * 4, w, "Blue males (of 200)",
                   0, TOTAL_MALES, self.params["blue_males"], "{:.0f}", step=1),
            Slider(x0, y + gap * 5, w, "Blue females (of 8)",
                   0, TOTAL_FEMALES, self.params["blue_females"], "{:.0f}", step=1),
            Slider(x0, y + gap * 6, w, "Max generations",
                   10, 5000, self.params["max_generations"], "{:.0f}", step=10),
            Slider(x0, y + gap * 7, w, "Blue preferred direction",
                   0, 360, self.params["blue_pref_deg"], "{:.0f}", step=5, unit="°"),
        ]

        bx = x0
        by = y + gap * 8 + 20
        self.btn_start = Button(bx, by, 220, 50, "INICIAR",
                                self._start_sim, color=(60, 140, 90))
        self.btn_reset = Button(bx + 240, by, 140, 50, "PADRÃO",
                                self._reset_defaults, color=(80, 80, 120))
        self.btn_quit = Button(bx + 400, by, 100, 50, "SAIR",
                               self._quit, color=(120, 60, 60))

    def _reset_defaults(self):
        defaults = {
            "pheromone": DEFAULT_PHEROMONE,
            "friction": DEFAULT_FRICTION,
            "base_accel": DEFAULT_BASE_ACCEL,
            "bias_strength": DEFAULT_BIAS_STRENGTH,
            "blue_males": 100,
            "blue_females": 4,
            "max_generations": MAX_GENERATIONS_DEFAULT,
            "blue_pref_deg": 0.0,
        }
        keys = ["pheromone", "friction", "base_accel", "bias_strength",
                "blue_males", "blue_females", "max_generations", "blue_pref_deg"]
        for s, k in zip(self.sliders, keys):
            s.value = defaults[k]
            self.params[k] = defaults[k]

    def _pull_params(self):
        keys = ["pheromone", "friction", "base_accel", "bias_strength",
                "blue_males", "blue_females", "max_generations", "blue_pref_deg"]
        for s, k in zip(self.sliders, keys):
            self.params[k] = s.value

    def _start_sim(self):
        self._pull_params()
        self.sim = Simulation(self.params)
        self.state = "sim"
        self.paused = False
        self.speed_multiplier = 1

    def _quit(self):
        pygame.quit()
        sys.exit(0)

    def _back_to_setup(self):
        self.state = "setup"
        self.sim = None

    # --------------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------------
    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if self.state == "setup":
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        running = False
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                        self._start_sim()
                    for s in self.sliders:
                        s.handle_event(event)
                    self.btn_start.handle_event(event)
                    self.btn_reset.handle_event(event)
                    self.btn_quit.handle_event(event)

                elif self.state == "sim":
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            running = False
                        elif event.key == pygame.K_p:
                            self.paused = not self.paused
                        elif event.key == pygame.K_r:
                            self._back_to_setup()
                        elif event.key == pygame.K_SPACE:
                            self.speed_multiplier = 10 if self.speed_multiplier == 1 else 1

            if self.state == "sim" and self.sim and not self.paused and not self.sim.finished:
                for _ in range(self.speed_multiplier):
                    self.sim.step()
                    if self.sim.finished:
                        break

            if self.state == "setup":
                self._draw_setup()
            else:
                self._draw_sim()

            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()

    # --------------------------------------------------------
    # SETUP SCREEN
    # --------------------------------------------------------
    def _draw_setup(self):
        self.screen.fill(C_BG)

        title = self.font_huge.render("Simulador de Insetos", True, C_TEXT)
        self.screen.blit(title, (60, 30))
        sub = self.font_small.render(
            "Ajuste os parâmetros e pressione INICIAR ou Enter.  ESC para sair.",
            True, C_TEXT_DIM)
        self.screen.blit(sub, (60, 75))

        for s in self.sliders:
            s.draw(self.screen, self.font, self.font_small)

        self.btn_start.draw(self.screen, self.font)
        self.btn_reset.draw(self.screen, self.font)
        self.btn_quit.draw(self.screen, self.font)

        # Painel de resumo à direita
        self._pull_params()
        px = 640
        py = 100
        self.screen.blit(self.font_big.render("Resumo", True, C_ACCENT), (px, py - 30))
        bm = int(self.params["blue_males"])
        bf = int(self.params["blue_females"])
        lines = [
            ("Pheromone", f"{self.params['pheromone']:.3f}"),
            ("Friction", f"{self.params['friction']:.4f}"),
            ("Base accel", f"{self.params['base_accel']:.3f}"),
            ("Bias strength", f"{self.params['bias_strength']:.3f}"),
            ("", ""),
            ("Machos azuis", f"{bm}"),
            ("Machos vermelhos", f"{TOTAL_MALES - bm}"),
            ("Fêmeas azuis", f"{bf}"),
            ("Fêmeas vermelhas", f"{TOTAL_FEMALES - bf}"),
            ("", ""),
            ("Max gerações", f"{int(self.params['max_generations'])}"),
            ("Direção azul", f"{self.params['blue_pref_deg']:.0f}°"),
        ]
        for i, (label, val) in enumerate(lines):
            if not label:
                py += 12
                continue
            ls = self.font_small.render(label, True, C_TEXT_DIM)
            vs = self.font.render(val, True, C_TEXT)
            self.screen.blit(ls, (px, py + 22 * i))
            self.screen.blit(vs, (px + 200, py + 22 * i - 2))

        # Bússola de direção
        ang = math.radians(self.params["blue_pref_deg"])
        cx, cy = px + 130, py + 340
        pygame.draw.circle(self.screen, C_PANEL_LIGHT, (cx, cy), 70, 2)
        pygame.draw.circle(self.screen, C_TEXT_DIM, (cx, cy), 3)
        for k in range(8):
            a = k * math.pi / 4
            x1 = cx + math.cos(a) * 60
            y1 = cy + math.sin(a) * 60
            x2 = cx + math.cos(a) * 70
            y2 = cy + math.sin(a) * 70
            pygame.draw.line(self.screen, C_TEXT_DIM, (x1, y1), (x2, y2), 1)
        dx = math.cos(ang) * 55
        dy = math.sin(ang) * 55
        pygame.draw.line(self.screen, C_ACCENT, (cx, cy), (cx + dx, cy + dy), 3)
        pygame.draw.circle(self.screen, C_ACCENT, (int(cx + dx), int(cy + dy)), 7)

    # --------------------------------------------------------
    # SIM SCREEN
    # --------------------------------------------------------
    def _draw_sim(self):
        self.screen.fill(C_BG)

        # Área da simulação
        pygame.draw.rect(self.screen, (8, 8, 14), pygame.Rect(0, 0, SIM_W, SIM_H))

        if self.sim:
            # Trail com surface reaproveitada
            surf = self.sim.trail_surf
            surf.fill((0, 0, 0, 0))
            for f in self.sim.females:
                vlen = f.vel.length()
                if vlen > 0:
                    d = f.vel / vlen
                else:
                    d = Vector2(1, 0)
                base = f.pos - d * TRAIL_LENGTH
                perp = Vector2(-d.y, d.x)
                half = TRAIL_LENGTH * math.tan(TRAIL_HALF_ANGLE)
                a = f.pos
                b = base + perp * half
                c = base - perp * half
                color = C_TRAIL_BLUE if f.is_biased else C_TRAIL_RED
                pygame.draw.polygon(surf, color, [a, b, c])
            self.screen.blit(surf, (0, 0))

            # Machos
            for m in self.sim.males:
                color = C_BLUE_MALE if m.is_biased else C_RED_MALE
                pygame.draw.circle(self.screen, color,
                                   (int(m.pos.x), int(m.pos.y)), MALE_RADIUS)

            # Fêmeas
            for f in self.sim.females:
                color = C_BLUE_FEMALE if f.is_biased else C_RED_FEMALE
                pygame.draw.circle(self.screen, color,
                                   (int(f.pos.x), int(f.pos.y)), FEMALE_RADIUS)
                pygame.draw.circle(self.screen, C_TEXT,
                                   (int(f.pos.x), int(f.pos.y)), FEMALE_RADIUS, 1)

        # Painel
        pygame.draw.rect(self.screen, C_PANEL,
                         pygame.Rect(PANEL_X - 10, 0, PANEL_W + 20, WINDOW_H))

        px = PANEL_X
        py = 20
        self.screen.blit(self.font_huge.render("Simulação", True, C_TEXT), (px, py))
        py += 50

        if self.sim:
            s = self.sim
            bm = sum(1 for m in s.males if m.is_biased)
            rm = len(s.males) - bm
            bf = sum(1 for f in s.females if f.is_biased)
            rf = len(s.females) - bf

            rows = [
                ("Geração", f"{s.generation}"),
                ("Cópulas", f"{s.copulation_count} / {COPULATIONS_PER_GEN}"),
                ("", ""),
                ("Azul-Azul", f"{s.n1}"),
                ("Verm-Verm", f"{s.n2}"),
                ("Azul-Verm", f"{s.n3}"),
                ("Verm-Azul", f"{s.n4}"),
                ("", ""),
                ("Machos azuis", f"{bm}"),
                ("Machos verm.", f"{rm}"),
                ("Fêmeas azuis", f"{bf}"),
                ("Fêmeas verm.", f"{rf}"),
                ("", ""),
                ("Direção azul", f"{math.degrees(s.blue_pref_angle) % 360:.0f}°"),
                ("Velocidade", f"×{self.speed_multiplier}"),
            ]
            for label, val in rows:
                if not label:
                    py += 10
                    continue
                ls = self.font_small.render(label, True, C_TEXT_DIM)
                vs = self.font.render(val, True, C_TEXT)
                self.screen.blit(ls, (px, py))
                self.screen.blit(vs, (px + 170, py - 2))
                py += 26

            # Estado
            py += 10
            if s.finished:
                if s.winner == "azul":
                    color = C_SUCCESS
                    msg = f"AZUL fixou em {s.finished_generation} ger."
                elif s.winner == "vermelho":
                    color = C_WARN
                    msg = f"VERMELHO fixou em {s.finished_generation} ger."
                else:
                    color = C_WARN
                    msg = f"Inconclusivo em {s.finished_generation} ger."
                ms = self.font.render(msg, True, color)
                self.screen.blit(ms, (px, py))
                py += 34
            elif self.paused:
                self.screen.blit(self.font.render("PAUSADO", True, C_WARN), (px, py))
                py += 34

            # Parâmetros ativos
            py += 10
            self.screen.blit(self.font.render("Parâmetros ativos", True, C_ACCENT),
                             (px, py))
            py += 30
            p = self.sim.params
            for label, val in [
                ("pheromone", f"{p['pheromone']:.3f}"),
                ("friction", f"{p['friction']:.4f}"),
                ("base accel", f"{p['base_accel']:.3f}"),
                ("bias", f"{p['bias_strength']:.3f}"),
            ]:
                ls = self.font_small.render(label, True, C_TEXT_DIM)
                vs = self.font_small.render(val, True, C_TEXT)
                self.screen.blit(ls, (px, py))
                self.screen.blit(vs, (px + 170, py))
                py += 22

        # Dica de teclas
        hint = self.font_small.render(
            "P=pausa  R=setup  Espaço=×10  ESC=sair",
            True, C_TEXT_DIM)
        self.screen.blit(hint, (px, WINDOW_H - 30))


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    App().run()