"""
Insects_DS15.py — v3
Simulacao padrao (identica a Insects_DS4.py) + Ilustracao interativa.
"""

import sys
import math
import random
import datetime

print("[DS15] importando pygame...", flush=True)
import pygame
from pygame.math import Vector2
print("[DS15] pygame importado com sucesso.", flush=True)

# ---------------- Constantes ----------------
WIDTH, HEIGHT = 1530, 800
FPS = 60

MALES_PER_GENERATION = 200
FEMALES_PER_GENERATION = 8
COPULATIONS_PER_GENERATION = 50
MALE_OFFSPRING_PER_COPULATION = 4

assert COPULATIONS_PER_GENERATION * MALE_OFFSPRING_PER_COPULATION == MALES_PER_GENERATION

BASE_ACCEL = 0.21
PHEROMONE_ACCEL = 0.65
FRICTION = 0.97
PREFERENCE_CORRECTION = 0.05
INITIAL_SPEED = 2.0

TRAIL_LENGTH = 310
TRAIL_HALF_ANGLE = math.radians(10)

BLUE = "blue"
RED = "red"

PH_CHOICES = [0.35, 0.45, 0.55, 0.65, 0.75, 0.85]
FR_CHOICES = [0.90, 0.93, 0.95, 0.97, 0.99]
PH_DEFAULT_INDEX = 3
FR_DEFAULT_INDEX = 3

MODE_STANDARD = "simulation"
MODE_ILLUSTRATION = "illustration"

TOROIDAL_MODE = True

# ---------------- Estado global ----------------
males = []
females = []
explosions = []
generation_records = []

blue_directed = True
chosen_pheromone = PH_CHOICES[PH_DEFAULT_INDEX]
chosen_friction = FR_CHOICES[FR_DEFAULT_INDEX]
sim_mode = MODE_STANDARD

generation = 1
copulation_count = 0
mating_counts = {"BB": 0, "RR": 0, "BR": 0, "RB": 0}
offspring_blue_buffer = 0
offspring_red_buffer = 0
blue_pref_angle = 0.0
paused = False

extinct_color = None
extinction_generation = None
parent_pairs = []


# ---------------- Helpers ----------------
def draw_text_with_outline(surface, text, pos, font, color,
                           outline_color=(0, 0, 0), outline_width=1):
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx or dy:
                s = font.render(text, True, outline_color)
                surface.blit(s, (pos[0] + dx, pos[1] + dy))
    surface.blit(font.render(text, True, color), pos)


def point_in_triangle(p, a, b, c):
    def sign(p1, p2, p3):
        return (p1.x - p3.x) * (p2.y - p3.y) - (p2.x - p3.x) * (p1.y - p3.y)
    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def random_velocity(speed=INITIAL_SPEED):
    angle = random.uniform(0.0, 2.0 * math.pi)
    return Vector2(math.cos(angle), math.sin(angle)) * speed


def preferred_velocity(speed=INITIAL_SPEED):
    return Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle)) * speed


def uses_preferred_direction(color):
    return blue_directed and color == BLUE


def choose_spawn_velocity(color):
    return preferred_velocity() if uses_preferred_direction(color) else random_velocity()


def closest_index(values, target):
    return min(range(len(values)), key=lambda i: abs(values[i] - target))


# ---------------- Explosao ----------------
class Explosion:
    def __init__(self, pos, duration=10, radius=10):
        self.pos = Vector2(pos)
        self.duration = duration
        self.life = duration
        self.radius = radius

    def update(self):
        self.life -= 1

    def draw(self, screen):
        alpha = int(255 * max(0, self.life) / self.duration)
        surf = pygame.Surface((2 * self.radius, 2 * self.radius), pygame.SRCALPHA)
        pygame.draw.circle(surf, (255, 255, 0, alpha),
                           (self.radius, self.radius), self.radius)
        screen.blit(surf, (self.pos.x - self.radius, self.pos.y - self.radius))


# ---------------- Femea ----------------
class Female:
    def __init__(self, pos, vel, color):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.color = color
        self.radius = 7
        self.alive = True

    def update(self):
        # Femea azul direcionada: aplica correcao preferencial como os machos
        if uses_preferred_direction(self.color):
            pref = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle))
            current = self.vel.normalize() if self.vel.length_squared() else Vector2(1, 0)
            self.vel += (pref - current) * PREFERENCE_CORRECTION * INITIAL_SPEED

        self.pos += self.vel
        if TOROIDAL_MODE:
            self.pos.x %= WIDTH
            self.pos.y %= HEIGHT
        else:
            if not (0 <= self.pos.x <= WIDTH and 0 <= self.pos.y <= HEIGHT):
                self.alive = False

    def trail_vertices(self):
        direction = self.vel.normalize() if self.vel.length_squared() else Vector2(1, 0)
        base_center = self.pos - direction * TRAIL_LENGTH
        base_half = TRAIL_LENGTH * math.tan(TRAIL_HALF_ANGLE)
        perp = Vector2(-direction.y, direction.x)
        left = base_center + perp * base_half
        right = base_center - perp * base_half
        return self.pos, left, right

    def contains_point(self, point):
        a, b, c = self.trail_vertices()
        if point_in_triangle(point, a, b, c):
            return True
        if (point.x < TRAIL_LENGTH or point.x > WIDTH - TRAIL_LENGTH or
                point.y < TRAIL_LENGTH or point.y > HEIGHT - TRAIL_LENGTH):
            for ox in (-WIDTH, 0, WIDTH):
                for oy in (-HEIGHT, 0, HEIGHT):
                    if ox == 0 and oy == 0:
                        continue
                    shifted = Vector2(point.x + ox, point.y + oy)
                    if point_in_triangle(shifted, a, b, c):
                        return True
        return False

    def draw(self, screen, _cache=[None]):
        a, b, c = self.trail_vertices()
        rgb = (0, 90, 255) if self.color == BLUE else (255, 45, 45)
        if _cache[0] is None:
            _cache[0] = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        temp = _cache[0]
        temp.fill((0, 0, 0, 0))
        for ox in (-WIDTH, 0, WIDTH):
            for oy in (-HEIGHT, 0, HEIGHT):
                pygame.draw.polygon(
                    temp, (*rgb, 55),
                    [(a.x + ox, a.y + oy), (b.x + ox, b.y + oy), (c.x + ox, c.y + oy)]
                )
        screen.blit(temp, (0, 0))
        pygame.draw.circle(screen, rgb,
                           (round(self.pos.x), round(self.pos.y)), self.radius)


# ---------------- Macho ----------------
class Male:
    def __init__(self, pos, vel, color, record_trail=False):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.acc = Vector2()
        self.color = color
        self.radius = 4
        self.locked_female = None
        self.alive = True
        self.record_trail = record_trail
        self.trail_segments = []

    def _select_trail_if_needed(self, females_list):
        if self.locked_female is not None:
            if self.locked_female.alive and self.locked_female.contains_point(self.pos):
                return self.locked_female
            self.locked_female = None
        candidates = [f for f in females_list if f.alive and f.contains_point(self.pos)]
        if candidates:
            self.locked_female = random.choice(candidates)
        return self.locked_female

    def update(self, females_list):
        self.acc.update(0, 0)
        target = self._select_trail_if_needed(females_list)

        if target is not None:
            dx = target.pos.x - self.pos.x
            dy = target.pos.y - self.pos.y
            dx = (dx + WIDTH / 2) % WIDTH - WIDTH / 2
            dy = (dy + HEIGHT / 2) % HEIGHT - HEIGHT / 2
            to_female = Vector2(dx, dy)
            if to_female.length_squared():
                self.acc += to_female.normalize() * PHEROMONE_ACCEL
        else:
            if self.vel.length_squared():
                self.acc += self.vel.normalize() * BASE_ACCEL
            if uses_preferred_direction(self.color):
                pref = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle))
                current = self.vel.normalize() if self.vel.length_squared() else Vector2(1, 0)
                self.acc += (pref - current) * PREFERENCE_CORRECTION

        self.vel += self.acc
        self.vel *= FRICTION

        prev_pos = Vector2(self.pos)
        self.pos += self.vel

        if TOROIDAL_MODE:
            self.pos.x %= WIDTH
            self.pos.y %= HEIGHT
            if self.record_trail:
                ddx = abs(self.pos.x - prev_pos.x)
                ddy = abs(self.pos.y - prev_pos.y)
                if ddx <= WIDTH / 2 and ddy <= HEIGHT / 2:
                    self.trail_segments.append((prev_pos, Vector2(self.pos)))
        else:
            if self.record_trail:
                self.trail_segments.append((prev_pos, Vector2(self.pos)))
            if not (0 <= self.pos.x <= WIDTH and 0 <= self.pos.y <= HEIGHT):
                self.alive = False

    def draw(self, screen):
        rgb = (0, 90, 255) if self.color == BLUE else (255, 45, 45)
        pygame.draw.circle(screen, rgb,
                           (round(self.pos.x), round(self.pos.y)), self.radius)


# ---------------- Reproducao ----------------
def register_copulation(male, female):
    global copulation_count, offspring_blue_buffer, offspring_red_buffer

    if male.color == BLUE and female.color == BLUE:
        mating_counts["BB"] += 1
    elif male.color == RED and female.color == RED:
        mating_counts["RR"] += 1
    elif male.color == BLUE and female.color == RED:
        mating_counts["BR"] += 1
    else:
        mating_counts["RB"] += 1

    parent_pairs.append((male.color, female.color))

    if male.color == female.color:
        if male.color == BLUE:
            offspring_blue_buffer += MALE_OFFSPRING_PER_COPULATION
        else:
            offspring_red_buffer += MALE_OFFSPRING_PER_COPULATION
    else:
        for _ in range(MALE_OFFSPRING_PER_COPULATION):
            if random.random() < 0.5:
                offspring_blue_buffer += 1
            else:
                offspring_red_buffer += 1

    copulation_count += 1
    explosions.append(Explosion(female.pos))


def make_population(n_blue_males, n_red_males, n_blue_females, n_red_females):
    males.clear()
    females.clear()
    for color, count in ((BLUE, n_blue_males), (RED, n_red_males)):
        for _ in range(count):
            pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
            males.append(Male(pos, choose_spawn_velocity(color), color))
    for color, count in ((BLUE, n_blue_females), (RED, n_red_females)):
        for _ in range(count):
            pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
            females.append(Female(pos, choose_spawn_velocity(color), color))
    random.shuffle(males)
    random.shuffle(females)


def check_extinction():
    global extinct_color, extinction_generation
    if extinct_color is not None:
        return
    has_blue = any(m.color == BLUE for m in males) or any(f.color == BLUE for f in females)
    has_red = any(m.color == RED for m in males) or any(f.color == RED for f in females)
    if not has_blue:
        extinct_color = BLUE
        extinction_generation = generation
    elif not has_red:
        extinct_color = RED
        extinction_generation = generation


def next_generation():
    global generation, copulation_count, offspring_blue_buffer, offspring_red_buffer, blue_pref_angle

    if extinct_color is not None:
        return

    total = offspring_blue_buffer + offspring_red_buffer
    if total != MALES_PER_GENERATION:
        raise RuntimeError(f"Expected {MALES_PER_GENERATION}, got {total}.")

    new_blue_males = offspring_blue_buffer
    new_red_males = offspring_red_buffer

    new_blue_females = 0
    new_red_females = 0
    for _ in range(FEMALES_PER_GENERATION):
        father_color, mother_color = random.choice(parent_pairs)
        if father_color == mother_color:
            child_color = father_color
        else:
            child_color = BLUE if random.random() < 0.5 else RED
        if child_color == BLUE:
            new_blue_females += 1
        else:
            new_red_females += 1

    p_blue = new_blue_males / MALES_PER_GENERATION

    generation += 1
    generation_records.append(
        (generation, new_blue_males, new_red_males, new_blue_females, new_red_females, p_blue)
    )
    generation_records[:] = generation_records[-20:]

    copulation_count = 0
    mating_counts.update(BB=0, RR=0, BR=0, RB=0)
    offspring_blue_buffer = 0
    offspring_red_buffer = 0
    parent_pairs.clear()
    explosions.clear()

    blue_pref_angle = random.uniform(0.0, 2.0 * math.pi)
    make_population(new_blue_males, new_red_males, new_blue_females, new_red_females)


# ---------------- Desenho de radios ----------------
def draw_radio_row(screen, font_body, y, label, choices, selected_idx):
    label_surf = font_body.render(label, True, (255, 255, 255))
    screen.blit(label_surf, (WIDTH // 2 - 480, y))
    x = WIDTH // 2 - 200
    spacing = 110
    for i, value in enumerate(choices):
        cx, cy = x + i * spacing, y + 12
        pygame.draw.circle(screen, (220, 220, 220), (cx, cy), 10, 2)
        if i == selected_idx:
            pygame.draw.circle(screen, (255, 255, 0), (cx, cy), 6)
        col = (255, 255, 0) if i == selected_idx else (200, 200, 200)
        vs = font_body.render(f"{value:g}", True, col)
        screen.blit(vs, (cx + 18, y))


def draw_radio_bool(screen, font_body, y, label, options, selected_idx):
    label_surf = font_body.render(label, True, (255, 255, 255))
    screen.blit(label_surf, (WIDTH // 2 - 480, y))
    x = WIDTH // 2 - 200
    spacing = 220
    for i, opt_label in enumerate(options):
        cx, cy = x + i * spacing, y + 12
        pygame.draw.circle(screen, (220, 220, 220), (cx, cy), 10, 2)
        if i == selected_idx:
            pygame.draw.circle(screen, (255, 255, 0), (cx, cy), 6)
        col = (255, 255, 0) if i == selected_idx else (200, 200, 200)
        vs = font_body.render(opt_label, True, col)
        screen.blit(vs, (cx + 18, y))


# ---------------- Menu ----------------
def menu(screen, clock, font_title, font_body):
    global blue_directed, chosen_pheromone, chosen_friction, sim_mode

    slip_idx = closest_index(FR_CHOICES, chosen_friction)
    ph_idx = closest_index(PH_CHOICES, chosen_pheromone)
    directed_idx = 0 if blue_directed else 1
    mode_idx = 0 if sim_mode == MODE_STANDARD else 1
    active_row = 0

    row_y = {0: 220, 1: 320, 2: 420, 3: 520}
    x0 = WIDTH // 2 - 200
    HIT_R = 22

    def hit(mx, my, cx, cy):
        return (mx - cx) ** 2 + (my - cy) ** 2 <= HIT_R * HIT_R

    while True:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key == pygame.K_RETURN:
                    sim_mode = MODE_STANDARD if mode_idx == 0 else MODE_ILLUSTRATION
                    blue_directed = (directed_idx == 0)
                    chosen_pheromone = PH_CHOICES[ph_idx]
                    chosen_friction = FR_CHOICES[slip_idx]
                    return True
                elif event.key == pygame.K_UP:
                    active_row = (active_row - 1) % 4
                elif event.key == pygame.K_DOWN:
                    active_row = (active_row + 1) % 4
                elif event.key == pygame.K_LEFT:
                    if active_row == 0:
                        slip_idx = (slip_idx - 1) % len(FR_CHOICES)
                    elif active_row == 1:
                        ph_idx = (ph_idx - 1) % len(PH_CHOICES)
                    elif active_row == 2:
                        directed_idx = (directed_idx - 1) % 2
                    else:
                        mode_idx = (mode_idx - 1) % 2
                elif event.key == pygame.K_RIGHT:
                    if active_row == 0:
                        slip_idx = (slip_idx + 1) % len(FR_CHOICES)
                    elif active_row == 1:
                        ph_idx = (ph_idx + 1) % len(PH_CHOICES)
                    elif active_row == 2:
                        directed_idx = (directed_idx + 1) % 2
                    else:
                        mode_idx = (mode_idx + 1) % 2

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for i in range(len(FR_CHOICES)):
                    if hit(mx, my, x0 + i * 110, row_y[0] + 12):
                        slip_idx = i
                        active_row = 0
                for i in range(len(PH_CHOICES)):
                    if hit(mx, my, x0 + i * 110, row_y[1] + 12):
                        ph_idx = i
                        active_row = 1
                for i in range(2):
                    if hit(mx, my, x0 + i * 220, row_y[2] + 12):
                        directed_idx = i
                        active_row = 2
                for i in range(2):
                    if hit(mx, my, x0 + i * 220, row_y[3] + 12):
                        mode_idx = i
                        active_row = 3

        screen.fill((8, 8, 12))
        title = font_title.render("Nuptial flight - parameters", True, (255, 255, 255))
        screen.blit(title, ((WIDTH - title.get_width()) // 2, 120))

        draw_radio_row(screen, font_body, row_y[0], "SLIPPERINESS:", FR_CHOICES, slip_idx)
        draw_radio_row(screen, font_body, row_y[1], "PHEROMONE_ACCEL:", PH_CHOICES, ph_idx)
        draw_radio_bool(screen, font_body, row_y[2], "Blue directed:",
                        ["yes", "no"], directed_idx)
        draw_radio_bool(screen, font_body, row_y[3], "Mode:",
                        ["Simulation", "Illustration"], mode_idx)

        hint1 = font_body.render("Arrows change values; Up/Down switch row",
                                 True, (200, 200, 200))
        hint2 = font_body.render("ENTER starts; ESC quits",
                                 True, (200, 200, 200))
        screen.blit(hint1, ((WIDTH - hint1.get_width()) // 2, 620))
        screen.blit(hint2, ((WIDTH - hint2.get_width()) // 2, 660))
        pygame.display.flip()


# ---------------- Simulacao padrao ----------------
def start_simulation():
    global generation, copulation_count, offspring_blue_buffer, offspring_red_buffer
    global blue_pref_angle, paused, extinct_color, extinction_generation

    generation = 1
    copulation_count = 0
    mating_counts.update(BB=0, RR=0, BR=0, RB=0)
    offspring_blue_buffer = 0
    offspring_red_buffer = 0
    parent_pairs.clear()
    explosions.clear()
    generation_records.clear()
    paused = False
    extinct_color = None
    extinction_generation = None
    blue_pref_angle = random.uniform(0.0, 2.0 * math.pi)

    b_m, r_m, b_f, r_f = 100, 100, 4, 4
    generation_records.append((generation, b_m, r_m, b_f, r_f, b_m / MALES_PER_GENERATION))
    make_population(b_m, r_m, b_f, r_f)


def run_standard_loop(screen, clock, font_small, font_title, font_body):
    global paused, PHEROMONE_ACCEL, FRICTION, TOROIDAL_MODE

    TOROIDAL_MODE = True
    PHEROMONE_ACCEL = chosen_pheromone
    FRICTION = chosen_friction
    start_simulation()

    while True:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key == pygame.K_p:
                    paused = not paused
                elif event.key == pygame.K_r:
                    return True
                elif event.key == pygame.K_RETURN:
                    start_simulation()

        if not paused:
            for female in females:
                female.update()

            for i in range(len(males) - 1, -1, -1):
                male = males[i]
                male.update(females)

                if male.locked_female is not None:
                    collision_candidates = [male.locked_female]
                else:
                    collision_candidates = females

                for female in collision_candidates:
                    if (male.pos - female.pos).length() < male.radius + female.radius:
                        register_copulation(male, female)
                        del males[i]
                        break

                if copulation_count >= COPULATIONS_PER_GENERATION:
                    break

            if copulation_count >= COPULATIONS_PER_GENERATION:
                next_generation()

            check_extinction()

        for exp in explosions[:]:
            exp.update()
            if exp.life <= 0:
                explosions.remove(exp)

        screen.fill((0, 0, 0))
        for female in females:
            female.draw(screen)
        for male in males:
            male.draw(screen)
        for exp in explosions:
            exp.draw(screen)

        mode_text = "EXPERIMENT (blue directed)" if blue_directed else "CONTROL"
        labels = [
            f"Generation: {generation}    Mode: {mode_text}",
            f"PHEROMONE_ACCEL: {PHEROMONE_ACCEL:g}    SLIPPERINESS: {FRICTION:g}",
            f"Copulations: {copulation_count}/{COPULATIONS_PER_GENERATION}",
            "P pause   R restart/menu   ENTER restart now   ESC quit",
        ]
        for j, text in enumerate(labels):
            draw_text_with_outline(screen, text, (10, 8 + 22 * j),
                                   font_small, (245, 245, 245))

        if extinct_color is not None:
            fixed_color = RED if extinct_color == BLUE else BLUE
            msg = f"{fixed_color} fixed at generation {extinction_generation}"
            s = font_title.render(msg, True, (255, 255, 0))
            screen.blit(s, ((WIDTH - s.get_width()) // 2, HEIGHT // 2 - 40))

        if paused:
            s = font_title.render("PAUSED", True, (255, 255, 255))
            screen.blit(s, ((WIDTH - s.get_width()) // 2, HEIGHT // 2))

        pygame.display.flip()


# ---------------- Ilustracao ----------------
PANEL_W = 250


def draw_button(screen, rect, text, font):
    pygame.draw.rect(screen, (55, 110, 180), rect, border_radius=6)
    pygame.draw.rect(screen, (200, 200, 200), rect, 2, border_radius=6)
    txt = font.render(text, True, (255, 255, 255))
    screen.blit(txt, (rect.x + (rect.w - txt.get_width()) // 2,
                      rect.y + (rect.h - txt.get_height()) // 2))


def draw_radio_small(screen, rect, label, checked, font):
    pygame.draw.circle(screen, (220, 220, 220), rect.center, rect.w // 2, 2)
    if checked:
        pygame.draw.circle(screen, (255, 255, 0), rect.center, rect.w // 2 - 4)
    txt = font.render(label, True, (255, 255, 255))
    screen.blit(txt, (rect.right + 8, rect.y - 2))


def spawn_female_at_wall(color):
    """
    Cria femea numa das paredes, com velocidade apontando para dentro.

    Excecao: se for femea AZUL e blue_directed estiver ligado, ela
    entra pela parede OPOSTA a direcao preferencial e recebe a velocidade
    preferencial, para se alinhar com todos os outros azuis.
    """
    if color == BLUE and blue_directed:
        cx = math.cos(blue_pref_angle)
        cy = math.sin(blue_pref_angle)
        if abs(cx) > abs(cy):
            if cx > 0:
                pos = Vector2(6, random.uniform(60, HEIGHT - 60))
            else:
                pos = Vector2(WIDTH - 6, random.uniform(60, HEIGHT - 60))
        else:
            if cy > 0:
                pos = Vector2(random.uniform(60, WIDTH - 60), 6)
            else:
                pos = Vector2(random.uniform(60, WIDTH - 60), HEIGHT - 6)
        return Female(pos=pos, vel=preferred_velocity(), color=color)

    side = random.choice(["left", "right", "top", "bottom"])
    if side == "left":
        pos = Vector2(6, random.uniform(60, HEIGHT - 60))
        vel = Vector2(1.0, random.uniform(-0.3, 0.3))
    elif side == "right":
        pos = Vector2(WIDTH - 6, random.uniform(60, HEIGHT - 60))
        vel = Vector2(-1.0, random.uniform(-0.3, 0.3))
    elif side == "top":
        pos = Vector2(random.uniform(60, WIDTH - 60), 6)
        vel = Vector2(random.uniform(-0.3, 0.3), 1.0)
    else:
        pos = Vector2(random.uniform(60, WIDTH - 60), HEIGHT - 6)
        vel = Vector2(random.uniform(-0.3, 0.3), -1.0)
    vel = vel.normalize() * INITIAL_SPEED
    return Female(pos=pos, vel=vel, color=color)


def illustration_screen(screen, clock, font_small, font_body, font_title):
    global TOROIDAL_MODE, PHEROMONE_ACCEL, FRICTION, blue_pref_angle

    PHEROMONE_ACCEL = chosen_pheromone
    FRICTION = chosen_friction
    blue_pref_angle = random.uniform(0.0, 2.0 * math.pi)

    male_color = BLUE
    version_multiple = True
    TOROIDAL_MODE = True

    trail_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

    local_females = []
    local_males = []
    local_explosions = []
    local_copula_marks = []

    local_females.append(spawn_female_at_wall(RED))

    pending_first_click = None
    paused = False
    pending_snapshot = False
    last_snapshot_name = ""

    btn_red_female  = pygame.Rect(20, 100, 210, 34)
    btn_blue_female = pygame.Rect(20, 144, 210, 34)
    lbl_male_y      = 200
    rb_blue_male    = pygame.Rect(20, lbl_male_y + 24, 18, 18)
    rb_red_male     = pygame.Rect(120, lbl_male_y + 24, 18, 18)
    lbl_ver_y       = 260
    rb_simple       = pygame.Rect(20, lbl_ver_y + 24, 18, 18)
    rb_multiple     = pygame.Rect(120, lbl_ver_y + 24, 18, 18)
    btn_erase       = pygame.Rect(20, 330, 210, 34)
    btn_snapshot    = pygame.Rect(20, 374, 210, 34)

    def draw_compass(surface):
        cx, cy, r = WIDTH - 70, 70, 34
        pygame.draw.circle(surface, (60, 60, 90), (cx, cy), r, 2)
        pygame.draw.circle(surface, (110, 110, 160), (cx, cy), 2)
        tip = (cx + (r - 6) * math.cos(blue_pref_angle),
               cy + (r - 6) * math.sin(blue_pref_angle))
        pygame.draw.line(surface, (120, 180, 255), (cx, cy), tip, 3)
        ax = tip[0] - 8 * math.cos(blue_pref_angle - 0.5)
        ay = tip[1] - 8 * math.sin(blue_pref_angle - 0.5)
        bx = tip[0] - 8 * math.cos(blue_pref_angle + 0.5)
        by = tip[1] - 8 * math.sin(blue_pref_angle + 0.5)
        pygame.draw.polygon(surface, (120, 180, 255),
                            [(tip[0], tip[1]), (ax, ay), (bx, by)])
        lbl = font_small.render("blue pref.", True, (150, 200, 255))
        surface.blit(lbl, (cx - lbl.get_width() // 2, cy + r + 6))

    while True:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    TOROIDAL_MODE = True
                    return True
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_r:
                    trail_surface.fill((0, 0, 0, 0))
                    local_copula_marks.clear()
                elif event.key == pygame.K_s:
                    pending_snapshot = True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos

                if btn_red_female.collidepoint(mx, my):
                    local_females.append(spawn_female_at_wall(RED))
                    continue
                if btn_blue_female.collidepoint(mx, my):
                    local_females.append(spawn_female_at_wall(BLUE))
                    continue
                if rb_blue_male.collidepoint(mx, my):
                    male_color = BLUE
                    continue
                if rb_red_male.collidepoint(mx, my):
                    male_color = RED
                    continue
                if rb_simple.collidepoint(mx, my):
                    version_multiple = False
                    TOROIDAL_MODE = False
                    continue
                if rb_multiple.collidepoint(mx, my):
                    version_multiple = True
                    TOROIDAL_MODE = True
                    continue
                if btn_erase.collidepoint(mx, my):
                    trail_surface.fill((0, 0, 0, 0))
                    local_copula_marks.clear()
                    continue
                if btn_snapshot.collidepoint(mx, my):
                    pending_snapshot = True
                    continue

                if mx < PANEL_W:
                    continue

                if pending_first_click is None:
                    pending_first_click = (mx, my)
                else:
                    px, py = pending_first_click
                    d = Vector2(mx - px, my - py)
                    if d.length_squared() > 4:
                        d = d.normalize() * INITIAL_SPEED
                        local_males.append(
                            Male(Vector2(px, py), d, male_color, record_trail=True)
                        )
                    pending_first_click = None

        if not paused:
            for f in local_females:
                f.update()
            local_females = [f for f in local_females if f.alive]

            for m in local_males:
                m.update(local_females)

                trail_color = (255, 120, 120) if m.color == RED else (120, 180, 255)
                for seg_start, seg_end in m.trail_segments:
                    pygame.draw.line(trail_surface, trail_color,
                                     seg_start, seg_end, 1)
                m.trail_segments.clear()

                if m.alive:
                    if m.locked_female is not None and m.locked_female.alive:
                        candidates = [m.locked_female]
                    else:
                        candidates = local_females
                    for f in candidates:
                        if (m.pos - f.pos).length() < m.radius + f.radius:
                            local_copula_marks.append((Vector2(m.pos), m.color))
                            if version_multiple:
                                local_explosions.append(
                                    Explosion(m.pos, duration=30, radius=18)
                                )
                            m.alive = False
                            break

            local_males = [m for m in local_males if m.alive]

            for e in local_explosions[:]:
                e.update()
                if e.life <= 0:
                    local_explosions.remove(e)

        # ---- Render ----
        screen.fill((0, 0, 0))
        for x in range(PANEL_W, WIDTH, 60):
            pygame.draw.line(screen, (18, 18, 22), (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, 60):
            pygame.draw.line(screen, (18, 18, 22), (PANEL_W, y), (WIDTH, y))

        screen.blit(trail_surface, (0, 0))

        for (pos, color) in local_copula_marks:
            pygame.draw.circle(screen, (255, 255, 0), (int(pos.x), int(pos.y)), 5)
            pygame.draw.circle(screen, (255, 80, 80), (int(pos.x), int(pos.y)), 5, 2)

        for f in local_females:
            f.draw(screen)
        for m in local_males:
            m.draw(screen)
        for e in local_explosions:
            e.draw(screen)

        if pending_first_click is not None:
            pygame.draw.circle(screen, (255, 220, 60), pending_first_click, 8, 2)
            pygame.draw.line(screen, (255, 220, 60),
                             pending_first_click, pygame.mouse.get_pos(), 1)

        if blue_directed:
            draw_compass(screen)

        panel_bg = pygame.Surface((PANEL_W, HEIGHT), pygame.SRCALPHA)
        panel_bg.fill((20, 20, 26, 235))
        screen.blit(panel_bg, (0, 0))

        draw_button(screen, btn_red_female,  "Create red female",  font_body)
        draw_button(screen, btn_blue_female, "Create blue female", font_body)

        lbl = font_body.render("Male color:", True, (255, 255, 255))
        screen.blit(lbl, (20, lbl_male_y))
        draw_radio_small(screen, rb_blue_male, "Blue", male_color == BLUE, font_body)
        draw_radio_small(screen, rb_red_male,  "Red",  male_color == RED,  font_body)

        lbl = font_body.render("Version:", True, (255, 255, 255))
        screen.blit(lbl, (20, lbl_ver_y))
        draw_radio_small(screen, rb_simple,   "Simple",   not version_multiple, font_body)
        draw_radio_small(screen, rb_multiple, "Multiple", version_multiple,     font_body)

        draw_button(screen, btn_erase,    "Erase trails", font_body)
        draw_button(screen, btn_snapshot, "Snapshot PNG", font_body)

        hud = [
            f"PHEROMONE_ACCEL = {PHEROMONE_ACCEL:g}    SLIPPERINESS = {FRICTION:g}",
            "Click 1: position   Click 2: direction",
            "SPACE pause   R erase   S snapshot   ESC back to menu",
        ]
        for j, t in enumerate(hud):
            txt = font_small.render(t, True, (200, 200, 200))
            screen.blit(txt, (PANEL_W + 12, HEIGHT - 80 + j * 22))

        if last_snapshot_name:
            txt = font_small.render(f"saved: {last_snapshot_name}", True, (150, 255, 150))
            screen.blit(txt, (PANEL_W + 12, HEIGHT - 14))

        if paused:
            s = font_title.render("PAUSED", True, (255, 255, 255))
            screen.blit(s, ((WIDTH - s.get_width()) // 2, HEIGHT // 2))

        pygame.display.flip()

        if pending_snapshot:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"snapshot_{ts}.png"
            pygame.image.save(screen, filename)
            print(f"[snapshot] {filename}", flush=True)
            last_snapshot_name = filename
            pending_snapshot = False


# ---------------- Main ----------------
def main():
    print("[DS15] pygame.init()...", flush=True)
    pygame.init()
    print("[DS15] criando janela...", flush=True)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Insects DS15 - simulation & illustration")
    clock = pygame.time.Clock()
    print("[DS15] janela pronta.", flush=True)

    font_small = pygame.font.SysFont(None, 23)
    font_body  = pygame.font.SysFont(None, 28)
    font_title = pygame.font.SysFont(None, 48)

    running = True
    while running:
        print("[DS15] entrando no menu...", flush=True)
        if not menu(screen, clock, font_title, font_body):
            break
        print(f"[DS15] menu confirmado. sim_mode={sim_mode}", flush=True)
        if sim_mode == MODE_STANDARD:
            print("[DS15] iniciando simulacao padrao...", flush=True)
            if not run_standard_loop(screen, clock, font_small, font_title, font_body):
                break
        else:
            print("[DS15] iniciando ilustracao...", flush=True)
            if not illustration_screen(screen, clock, font_small, font_body, font_title):
                break

    print("[DS15] encerrando.", flush=True)
    pygame.quit()

# ---------------- Headless API (para o batch) ----------------
def run_headless(pheromone, friction, blue_directed_flag, seed=None, progress_cb=None):
    """
    Roda a simulacao completa sem pygame, sem menu, sem desenho.
    Mesma assinatura do Insects_DS4.py.
    Retorna (fixed_color, fixation_generation).
    """
    global PHEROMONE_ACCEL, FRICTION, blue_directed, TOROIDAL_MODE
    global generation, copulation_count, offspring_blue_buffer, offspring_red_buffer
    global blue_pref_angle, paused, extinct_color, extinction_generation

    TOROIDAL_MODE = True
    PHEROMONE_ACCEL = float(pheromone)
    FRICTION = float(friction)
    blue_directed = bool(blue_directed_flag)

    if seed is not None:
        random.seed(int(seed))
    else:
        random.seed()

    generation = 1
    copulation_count = 0
    mating_counts.update(BB=0, RR=0, BR=0, RB=0)
    offspring_blue_buffer = 0
    offspring_red_buffer = 0
    parent_pairs.clear()
    explosions.clear()
    generation_records.clear()
    paused = False
    extinct_color = None
    extinction_generation = None
    blue_pref_angle = random.uniform(0.0, 2.0 * math.pi)

    b_m, r_m, b_f, r_f = 100, 100, 4, 4
    generation_records.append((generation, b_m, r_m, b_f, r_f, b_m / MALES_PER_GENERATION))
    make_population(b_m, r_m, b_f, r_f)

    while extinct_color is None:
        for female in females:
            female.update()

        for i in range(len(males) - 1, -1, -1):
            male = males[i]
            male.update(females)

            if male.locked_female is not None:
                collision_candidates = [male.locked_female]
            else:
                collision_candidates = females

            for female in collision_candidates:
                if (male.pos - female.pos).length() < male.radius + female.radius:
                    register_copulation(male, female)
                    del males[i]
                    break

            if copulation_count >= COPULATIONS_PER_GENERATION:
                break

        if copulation_count >= COPULATIONS_PER_GENERATION:
            next_generation()
            if progress_cb is not None:
                progress_cb(generation)

        check_extinction()

    fixed_color = RED if extinct_color == BLUE else BLUE
    return fixed_color, extinction_generation


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        try:
            input("\nOcorreu um erro. Pressione ENTER para fechar...")
        except EOFError:
            pass
