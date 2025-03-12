# Insects-Code

import pygame
import random
import math
from pygame.math import Vector2

# ----- Dimensões da Janela -----
WIDTH = 800
HEIGHT = 800

# ----- Parâmetros de Física -----
baseAccel = 0.21       # aceleração base fora do rastro
pheromoneAccel = 0.65  # aceleração extra dentro do rastro
friction = 0.97        # fator de viscosidade/inércia

# ----- Variáveis de Controle da Simulação -----
n1 = 0  # macho azul - fêmea azul (copulação)
n2 = 0  # macho vermelho - fêmea vermelha
n3 = 0  # macho azul - fêmea vermelha
n4 = 0  # macho vermelho - fêmea azul
copulationCount = 0  # total de cópulas (até 100)

generation = 1  # número da geração

# Variáveis para controle de fêmeas (serão redefinidas no reset_simulation)
blueFemalesCount = 0
redFemalesCount = 0

# Ângulo de preferência (usado pelos machos azuis quando aplicável)
bluePrefAngle = random.uniform(0, 2 * math.pi)

paused = False
simulationEnded = False
extinctionMessage = ""

# Listas dos indivíduos
males = []    # Lista dos machos
females = []  # Lista das fêmeas

# Lista para as explosões (para denotar cópulas)
explosions = []

# Registro das gerações para exibição (últimas 20 gerações)
# Cada registro: (geração, machos_azuis, machos_vermelhos, fêmeas_azuis, fêmeas_vermelhas)
generation_records = []

# Variável que guarda o modo de simulação escolhido ("mutant" ou "balanced")
simulation_mode = None

# ----- Função Auxiliar para desenhar texto com contorno -----
def draw_text_with_outline(surface, text, pos, font, color, outline_color, outline_width=2):
    text_surface = font.render(text, True, color)
    for dx in range(-outline_width, outline_width+1):
        for dy in range(-outline_width, outline_width+1):
            if dx != 0 or dy != 0:
                outline_surf = font.render(text, True, outline_color)
                surface.blit(outline_surf, (pos[0]+dx, pos[1]+dy))
    surface.blit(text_surface, pos)

# ----- Classe para a Explosão (cópula) -----
class Explosion:
    def __init__(self, pos, duration=10, radius=10):
        self.pos = Vector2(pos)
        self.duration = duration
        self.life = duration
        self.radius = radius
    def update(self):
        self.life -= 1
    def draw(self, screen):
        alpha = int(255 * (self.life / self.duration))
        surf = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (255, 255, 0, alpha), (self.radius, self.radius), self.radius)
        screen.blit(surf, (self.pos.x - self.radius, self.pos.y - self.radius))

# ----- Função Auxiliar: Testa se um ponto está dentro de um triângulo -----
def point_in_triangle(p, a, b, c):
    def sign(p1, p2, p3):
        return (p1.x - p3.x) * (p2.y - p3.y) - (p2.x - p3.x) * (p1.y - p3.y)
    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)

# ----- Classes dos Indivíduos -----
class Male:
    def __init__(self, pos, vel, type_):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.acc = Vector2(0, 0)
        self.type = type_  # "azul" ou "vermelho"
        self.radius = 4

    def update(self):
        global bluePrefAngle
        self.acc = Vector2(0, 0)
        in_trail = False
        for f in females:
            if f.contains_point(self.pos):
                in_trail = True
                to_female = f.pos - self.pos
                if to_female.length() != 0:
                    to_female = to_female.normalize() * pheromoneAccel
                self.acc += to_female
                break
        if not in_trail:
            if self.vel.length() != 0:
                baseDir = self.vel.normalize() * baseAccel
                self.acc += baseDir
            if self.type == "azul":
                pref = Vector2(math.cos(bluePrefAngle), math.sin(bluePrefAngle))
                currentDir = self.vel.normalize() if self.vel.length() != 0 else Vector2(1, 0)
                correction = (pref - currentDir) * 0.05
                self.acc += correction
        self.vel += self.acc
        self.vel *= friction
        self.pos += self.vel
        if self.pos.x < 0:
            self.pos.x += WIDTH
        if self.pos.x > WIDTH:
            self.pos.x -= WIDTH
        if self.pos.y < 0:
            self.pos.y += HEIGHT
        if self.pos.y > HEIGHT:
            self.pos.y -= HEIGHT

    def draw(self, screen):
        color = (0, 0, 255) if self.type == "azul" else (255, 0, 0)
        pygame.draw.circle(screen, color, (int(self.pos.x), int(self.pos.y)), self.radius)

class Female:
    def __init__(self, pos, vel, type_):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.type = type_  # "azul" ou "vermelha"
        self.radius = 7

    def update(self):
        self.pos += self.vel
        if self.pos.x < 0:
            self.pos.x += WIDTH
        if self.pos.x > WIDTH:
            self.pos.x -= WIDTH
        if self.pos.y < 0:
            self.pos.y += HEIGHT
        if self.pos.y > HEIGHT:
            self.pos.y -= HEIGHT

    def draw(self, screen):
        tailLength = 310
        halfAngle = math.radians(10)
        direction = self.vel.normalize() if self.vel.length() != 0 else Vector2(1, 0)
        baseCenter = self.pos - direction * tailLength
        baseHalf = tailLength * math.tan(halfAngle)
        perp = Vector2(-direction.y, direction.x)
        left = baseCenter + perp * baseHalf
        right = baseCenter - perp * baseHalf
        color = (0, 0, 255) if self.type == "azul" else (255, 0, 0)
        temp = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.polygon(temp, (color[0], color[1], color[2], 80),
                            [(self.pos.x, self.pos.y), (left.x, left.y), (right.x, right.y)])
        screen.blit(temp, (0, 0))
        pygame.draw.circle(screen, color, (int(self.pos.x), int(self.pos.y)), self.radius)

    def contains_point(self, point):
        tailLength = 310
        halfAngle = math.radians(10)
        direction = self.vel.normalize() if self.vel.length() != 0 else Vector2(1, 0)
        baseCenter = self.pos - direction * tailLength
        baseHalf = tailLength * math.tan(halfAngle)
        perp = Vector2(-direction.y, direction.x)
        left = baseCenter + perp * baseHalf
        right = baseCenter - perp * baseHalf
        return point_in_triangle(point, self.pos, left, right)

# ----- Função de Controle da Geração com Proporção de Fêmeas -----
def next_generation():
    global n1, n2, n3, n4, copulationCount, generation
    global blueFemalesCount, redFemalesCount, bluePrefAngle, males, females, generation_records
    global simulationEnded, extinctionMessage

    newBlueMales = 2 * n1 + n3 + n4
    newRedMales  = 2 * n2 + n3 + n4

    if newBlueMales <= 0:
        simulationEnded = True
        extinctionMessage = f"Geração {generation}\nExtinção do tipo azul"
        return
    if newRedMales <= 0:
        simulationEnded = True
        extinctionMessage = f"Geração {generation}\nExtinção do tipo vermelho"
        return

    if newBlueMales >= newRedMales:
        m = newBlueMales
        majority = "azul"
    else:
        m = newRedMales
        majority = "vermelho"

    if m > 74 and m < 126:
        blueFemalesCount = 4
        redFemalesCount = 4
    elif m > 125 and m < 151:
        if majority == "azul":
            blueFemalesCount = 5
            redFemalesCount = 3
        else:
            redFemalesCount = 5
            blueFemalesCount = 3
    elif m > 150 and m < 176:
        if majority == "azul":
            blueFemalesCount = 6
            redFemalesCount = 2
        else:
            redFemalesCount = 6
            blueFemalesCount = 2
    elif m > 175 and m < 188:
        if majority == "azul":
            blueFemalesCount = 7
            redFemalesCount = 1
        else:
            redFemalesCount = 7
            blueFemalesCount = 1
    elif m > 187:
        if majority == "azul":
            blueFemalesCount = 8
            redFemalesCount = 0
        else:
            redFemalesCount = 8
            blueFemalesCount = 0
    else:
        blueFemalesCount = 4
        redFemalesCount = 4

    generation += 1
    generation_records.append((generation, newBlueMales, newRedMales, blueFemalesCount, redFemalesCount))
    generation_records[:] = generation_records[-20:]

    copulationCount = 0
    n1 = n2 = n3 = n4 = 0
    males.clear()
    females.clear()
    bluePrefAngle = random.uniform(0, 2 * math.pi)

    for _ in range(newBlueMales):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(bluePrefAngle), math.sin(bluePrefAngle)) * 2
        males.append(Male(pos, vel, "azul"))
    for _ in range(newRedMales):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        angle = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(angle), math.sin(angle)) * 2
        males.append(Male(pos, vel, "vermelho"))
    for _ in range(blueFemalesCount):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(bluePrefAngle), math.sin(bluePrefAngle)) * 2
        females.append(Female(pos, vel, "azul"))
    for _ in range(redFemalesCount):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        angle = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(angle), math.sin(angle)) * 2
        females.append(Female(pos, vel, "vermelha"))

# ----- Função para exibir o Menu Inicial -----
def show_menu():
    global simulation_mode, paused, simulationEnded
    menu_active = True
    while menu_active:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    simulation_mode = "mutant"
                    menu_active = False
                elif event.key == pygame.K_2:
                    simulation_mode = "balanced"
                    menu_active = False
        screen.fill((0, 0, 0))
        menu_lines = [
            "Pressione 1 para simular uma",
            "única fêmea mutante",
            "",
            "Pressione 2 para população",
            "inicialmente equilibrada",
            "(metade de cada cor)"
        ]
        line_height = font_menu.get_linesize()
        total_height = line_height * len(menu_lines)
        start_y = (HEIGHT - total_height) // 2
        for i, line in enumerate(menu_lines):
            text_surface = font_menu.render(line.strip(), True, (255, 255, 255))
            x = (WIDTH - text_surface.get_width()) // 2
            y = start_y + i * line_height
            screen.blit(text_surface, (x, y))
        pygame.display.flip()
    paused = False
    simulationEnded = False

# ----- Função para resetar a simulação (retorna SEMPRE para o menu) -----
def reset_simulation():
    global simulation_mode, generation, copulationCount, n1, n2, n3, n4
    global blueFemalesCount, redFemalesCount, simulationEnded, extinctionMessage
    global males, females, bluePrefAngle, generation_records, explosions

    # Força o retorno ao menu de opções
    simulation_mode = None
    show_menu()

    generation = 1
    copulationCount = 0
    n1 = n2 = n3 = n4 = 0
    simulationEnded = False
    extinctionMessage = ""
    males.clear()
    females.clear()
    generation_records.clear()
    explosions.clear()
    bluePrefAngle = random.uniform(0, 2 * math.pi)

    if simulation_mode == "balanced":
        blueFemalesCount = 4
        redFemalesCount = 4
        generation_records.append((generation, 100, 100, blueFemalesCount, redFemalesCount))
        for _ in range(100):
            pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
            vel = Vector2(math.cos(bluePrefAngle), math.sin(bluePrefAngle)) * 2
            males.append(Male(pos, vel, "azul"))
        for _ in range(100):
            pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
            angle = random.uniform(0, 2 * math.pi)
            vel = Vector2(math.cos(angle), math.sin(angle)) * 2
            males.append(Male(pos, vel, "vermelho"))
        for _ in range(4):
            pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
            vel = Vector2(math.cos(bluePrefAngle), math.sin(bluePrefAngle)) * 2
            females.append(Female(pos, vel, "azul"))
        for _ in range(4):
            pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
            angle = random.uniform(0, 2 * math.pi)
            vel = Vector2(math.cos(angle), math.sin(angle)) * 2
            females.append(Female(pos, vel, "vermelha"))
    else:  # Modo "mutant": fêmea mutante
        blueFemalesCount = 1
        redFemalesCount = 7
        generation_records.append((generation, 0, 200, blueFemalesCount, redFemalesCount))
        for _ in range(200):
            pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
            angle = random.uniform(0, 2 * math.pi)
            vel = Vector2(math.cos(angle), math.sin(angle)) * 2
            males.append(Male(pos, vel, "vermelho"))
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(bluePrefAngle), math.sin(bluePrefAngle)) * 2
        females.append(Female(pos, vel, "azul"))
        for _ in range(7):
            pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
            angle = random.uniform(0, 2 * math.pi)
            vel = Vector2(math.cos(angle), math.sin(angle)) * 2
            females.append(Female(pos, vel, "vermelha"))

# ----- Inicialização do Pygame -----
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Voo Nupcial: Surgimento do Direcionamento")
clock = pygame.time.Clock()
font_top = pygame.font.SysFont(None, 24)
font_side = font_top
font_menu = pygame.font.SysFont(None, 72)

top_panel_height = 140
bottom_panel_height = 100

# Inicia diretamente com a simulação do tipo 2 (população equilibrada)
simulation_mode = "balanced"
reset_simulation()

# ----- Loop Principal -----
running = True
while running:
    clock.tick(60)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p:
                paused = not paused
            elif event.key == pygame.K_r:
                reset_simulation()

    if not paused and not simulationEnded:
        for f in females:
            f.update()
        for i in range(len(males) - 1, -1, -1):
            m = males[i]
            m.update()
            for f in females:
                if (m.pos - f.pos).length() < (m.radius + f.radius):
                    if m.type == "azul" and f.type == "azul":
                        n1 += 1
                    elif m.type == "vermelho" and f.type == "vermelha":
                        n2 += 1
                    elif m.type == "azul" and f.type == "vermelha":
                        n3 += 1
                    elif m.type == "vermelho" and f.type == "azul":
                        n4 += 1
                    copulationCount += 1
                    explosions.append(Explosion(f.pos, duration=10, radius=10))
                    del males[i]
                    break
        if copulationCount >= 100:
            next_generation()

    for exp in explosions[:]:
        exp.update()
        if exp.life <= 0:
            explosions.remove(exp)

    screen.fill((0, 0, 0))
    for f in females:
        f.draw(screen)
    for m in males:
        m.draw(screen)
    for exp in explosions:
        exp.draw(screen)

    top_panel = pygame.Surface((WIDTH, top_panel_height), pygame.SRCALPHA)
    top_panel.fill((0, 0, 0, 0))
    labels = [
        f"Geração: {generation}",
        f"Total de cópulas: {copulationCount}",
        f"Azul-Azul: {n1}",
        f"Vermelho-Vermelha: {n2}",
        f"Vermelho-Azul: {n3}",
        f"Azul-Vermelha: {n4}"
    ]
    for i, text in enumerate(labels):
        draw_text_with_outline(top_panel, text, (10, 10 + i * 22),
                               font_top, (255, 255, 255), (0, 0, 0), outline_width=1)
    screen.blit(top_panel, (0, 0))
    
    msg = "pressione r para reiniciar, p para pausar"
    msg_pos = (WIDTH - font_top.size(msg)[0] - 10, 10)
    draw_text_with_outline(screen, msg, msg_pos, font_top, (255,255,255), (0,0,0), outline_width=1)

    bottom_panel = pygame.Surface((WIDTH, bottom_panel_height), pygame.SRCALPHA)
    bottom_panel.fill((0, 0, 0, 0))
    regs = generation_records[-20:]
    col_width = WIDTH // 20
    for idx, rec in enumerate(regs):
        gen_num, blue_males, red_males, _, _ = rec
        x = idx * col_width + 5
        bottom_panel.blit(font_side.render(str(gen_num), True, (255, 255, 255)), (x, 5))
        bottom_panel.blit(font_side.render(str(blue_males), True, (0, 255, 0)), (x, 25))
        bottom_panel.blit(font_side.render(str(red_males), True, (255, 0, 0)), (x, 45))
    screen.blit(bottom_panel, (0, HEIGHT - bottom_panel_height))

    if paused:
        pause_surface = font_top.render("PAUSA", True, (255, 255, 255))
        screen.blit(pause_surface, (WIDTH // 2 - 30, HEIGHT // 2 - 10))
    if simulationEnded:
        for i, line in enumerate(extinctionMessage.split("\n")):
            ext_surface = font_top.render(line, True, (255, 255, 255))
            screen.blit(ext_surface, (WIDTH // 2 - 100, HEIGHT // 2 - 20 + i * 30))

    pygame.display.flip()

pygame.quit()
