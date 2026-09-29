"""
Insects_batch_DS17.py
Batch runner paralelo para Insects_DS15.py, com GUI.

Correcoes em relacao ao DS16:
  - Chave de checkpoint baseada em (pheromone, friction, blue_directed, replicate)
    em vez de (condition_id, replicate). Imune a mudancas de grid entre rodadas.
  - Validacao de parametros antes de rodar: rejeita SLIPPERINESS fora de
    [0.85, 1.00] e PHEROMONE fora de (0, 1). Avisa se slip < 0.90.
  - condition_id no summary e reatribuido de forma estavel, ordenado por
    (friction, pheromone, blue_directed). Nao ha mais duplicacao.
  - Opcao 'Fresh start' na GUI: apaga o CSV de saida antes de comecar.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import statistics
import time

from joblib import Parallel, delayed

import Insects_DS15 as sim

print(f"[IMPORT] simulation module = {sim.__file__}", flush=True)

DEFAULT_MAX_GENERATIONS = 10000

# Faixas aceitaveis (com avisos fora do "core")
SLIP_MIN_HARD = 0.85
SLIP_MAX_HARD = 1.00
SLIP_MIN_WARN = 0.90
PH_MIN_HARD = 0.05
PH_MAX_HARD = 0.95

RESULT_FIELDS = [
    "condition_id", "replicate", "seed", "pheromone", "friction",
    "blue_directed", "fixed_color", "fixation_generation", "runtime_seconds",
]
SUMMARY_FIELDS = [
    "condition_id", "pheromone", "friction", "blue_directed",
    "n_replicates", "n_blue", "n_red", "blue_fraction",
    "mean_generation", "median_generation", "sd_generation",
    "min_generation", "max_generation", "mean_runtime_seconds",
]


# ============================================================================
# Grid loader
# ============================================================================
def load_grid(path):
    conditions = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4:
                raise ValueError(f"grid line {line_no}: need >=4 fields")
            ph = float(parts[0])
            fr = float(parts[1])
            d = parts[2].lower()
            directed = d in ("yes", "true", "1", "y")
            reps = int(parts[3])
            mg = int(parts[4]) if len(parts) >= 5 else DEFAULT_MAX_GENERATIONS
            conditions.append({
                "pheromone": ph, "friction": fr,
                "blue_directed": directed,
                "replicates": reps, "max_generations": mg,
            })
    return conditions


def parse_list(text):
    text = text.replace(",", " ").strip()
    parts = [p for p in text.split() if p]
    return [float(p) for p in parts]


def build_conditions_from_cfg(cfg):
    conds = []
    for ph in cfg["pheromones"]:
        for slip in cfg["slipperiness"]:
            conds.append({
                "pheromone": ph,
                "friction": slip,
                "blue_directed": cfg["blue_directed"],
                "replicates": cfg["replicates"],
                "max_generations": DEFAULT_MAX_GENERATIONS,
            })
    return conds


# ============================================================================
# Validacao
# ============================================================================
def validate_cfg(cfg):
    """Retorna (ok, lista_de_avisos, lista_de_erros)."""
    warnings = []
    errors = []

    if not cfg["pheromones"]:
        errors.append("Lista de PHEROMONE vazia.")
    if not cfg["slipperiness"]:
        errors.append("Lista de SLIPPERINESS vazia.")

    for ph in cfg["pheromones"]:
        if not (PH_MIN_HARD < ph < PH_MAX_HARD):
            errors.append(
                f"PHEROMONE = {ph} fora do intervalo aceitavel "
                f"({PH_MIN_HARD}, {PH_MAX_HARD})."
            )

    for slip in cfg["slipperiness"]:
        if not (SLIP_MIN_HARD <= slip <= SLIP_MAX_HARD):
            errors.append(
                f"SLIPPERINESS = {slip} fora do intervalo aceitavel "
                f"[{SLIP_MIN_HARD}, {SLIP_MAX_HARD}]."
            )
        elif slip < SLIP_MIN_WARN:
            warnings.append(
                f"SLIPPERINESS = {slip} < {SLIP_MIN_WARN}: "
                f"pode degenerar o modelo (insetos quase imoveis)."
            )

    if cfg["replicates"] < 1:
        errors.append(f"Replicates = {cfg['replicates']} invalido.")
    if cfg["jobs"] == 0:
        errors.append("Parallel jobs nao pode ser 0.")

    return (len(errors) == 0), warnings, errors


# ============================================================================
# Seed
# ============================================================================
def stable_seed(base_seed, pheromone, friction, replicate):
    payload = f"{base_seed}|{pheromone!r}|{friction!r}|{replicate}"
    rng = random.Random(payload)
    return rng.randrange(1, 2**63 - 1)


# ============================================================================
# CSV
# ============================================================================
def append_result_csv(path, row):
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())


def load_completed_results(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def param_key(pheromone, friction, blue_directed, replicate):
    """Chave de deduplicacao robusta, baseada em parametros reais."""
    return (
        round(float(pheromone), 6),
        round(float(friction), 6),
        str(blue_directed).lower(),
        int(replicate),
    )


def blue_fraction_str(x):
    return "" if x == "" else f"{x:.4f}"


def write_summary_csv(path, rows):
    """
    Reagrupa por parametros. condition_id e reatribuido estavelmente,
    ordenado por (friction, pheromone, blue_directed).
    """
    # Filtra linhas validas
    valid = []
    for row in rows:
        if not row.get("fixed_color"):
            continue
        if any(k not in row for k in
               ("pheromone", "friction", "blue_directed", "replicate")):
            continue
        try:
            float(row["pheromone"]); float(row["friction"])
            int(row["replicate"])
        except (ValueError, TypeError):
            continue
        valid.append(row)

    # Agrupa por (ph, fr, directed) — nao usa condition_id
    groups = {}
    for row in valid:
        key = (
            round(float(row["pheromone"]), 6),
            round(float(row["friction"]), 6),
            str(row["blue_directed"]).lower(),
        )
        groups.setdefault(key, []).append(row)

    # Atribui condition_id estavel
    stable_ids = {}
    for i, key in enumerate(sorted(groups.keys()), 1):
        stable_ids[key] = i

    summary = []
    for key, group in groups.items():
        ph, fr, directed = key
        # Deduplica replicas: se a mesma (replicate) aparecer mais de uma vez
        # com mesma chave, mantemos apenas a ultima ocorrencia (mais recente).
        seen = {}
        for r in group:
            seen[int(r["replicate"])] = r
        group = list(seen.values())

        gens = [int(r["fixation_generation"]) for r in group
                if r["fixation_generation"] not in ("", None)]
        n_blue = sum(1 for r in group if r["fixed_color"] == "blue")
        n_red = sum(1 for r in group if r["fixed_color"] == "red")
        n_total = len(group)
        summary.append({
            "condition_id": stable_ids[key],
            "pheromone": ph,
            "friction": fr,
            "blue_directed": directed,
            "n_replicates": n_total,
            "n_blue": n_blue,
            "n_red": n_red,
            "blue_fraction": blue_fraction_str(n_blue / n_total if n_total else ""),
            "mean_generation": statistics.mean(gens) if gens else "",
            "median_generation": statistics.median(gens) if gens else "",
            "sd_generation": statistics.stdev(gens) if len(gens) >= 2 else "",
            "min_generation": min(gens) if gens else "",
            "max_generation": max(gens) if gens else "",
            "mean_runtime_seconds": statistics.mean(
                float(r["runtime_seconds"]) for r in group),
        })

    summary.sort(key=lambda s: (s["friction"], s["pheromone"], s["blue_directed"]))

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary)
    return summary


# ============================================================================
# Worker
# ============================================================================
def _run_one_replicate(cond_id, rep, ph, fr, directed, seed, max_gen):
    t0 = time.perf_counter()
    try:
        fixed_color, fixation_gen = sim.run_headless(
            pheromone=ph,
            friction=fr,
            blue_directed_flag=directed,
            seed=seed,
            progress_cb=None,
        )
    except Exception as e:
        return {
            "condition_id": cond_id, "replicate": rep, "seed": seed,
            "pheromone": ph, "friction": fr,
            "blue_directed": "yes" if directed else "no",
            "fixed_color": f"ERROR:{type(e).__name__}",
            "fixation_generation": "",
            "runtime_seconds": f"{time.perf_counter() - t0:.4f}",
        }
    dt = time.perf_counter() - t0
    return {
        "condition_id": cond_id,
        "replicate": rep,
        "seed": seed,
        "pheromone": ph,
        "friction": fr,
        "blue_directed": "yes" if directed else "no",
        "fixed_color": fixed_color if fixed_color else "",
        "fixation_generation": fixation_gen if fixation_gen else "",
        "runtime_seconds": f"{dt:.4f}",
    }


# ============================================================================
# GUI
# ============================================================================
def gui_menu():
    import pygame
    pygame.init()
    W, H = 1100, 880
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Batch runner DS17 - parameters")
    clock = pygame.time.Clock()
    font_title = pygame.font.SysFont(None, 40)
    font_body = pygame.font.SysFont(None, 24)
    font_small = pygame.font.SysFont(None, 20)

    directed_idx = 0  # 0 = yes, 1 = no
    fresh_start = False

    fields = [
        {"label": "PHEROMONE values (comma-separated)",
         "text": "0.35, 0.45, 0.55, 0.65, 0.75, 0.85"},
        {"label": "SLIPPERINESS values (comma-separated)",
         "text": "0.93, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99"},
        {"label": "Replicates per condition", "text": "30"},
        {"label": "Parallel jobs (-1 = all cores)", "text": "6"},
        {"label": "Base seed", "text": "42"},
        {"label": "Output CSV", "text": "batch_dir_results.csv"},
        {"label": "Summary CSV", "text": "batch_dir_summary.csv"},
    ]
    active = 0
    confirmed = None
    error_msg = ""
    warning_msg = ""

    x_label = 40
    x_field = 480
    field_w = W - x_field - 40
    y0 = 240
    row_h = 58

    def field_rect(i):
        return pygame.Rect(x_field, y0 + i * row_h, field_w, 34)

    def update_filename_if_default():
        """Troca o nome default conforme modo."""
        if directed_idx == 0:
            if fields[5]["text"] in ("batch_ctrl_results.csv",):
                fields[5]["text"] = "batch_dir_results.csv"
            if fields[6]["text"] in ("batch_ctrl_summary.csv",):
                fields[6]["text"] = "batch_dir_summary.csv"
        else:
            if fields[5]["text"] in ("batch_dir_results.csv",):
                fields[5]["text"] = "batch_ctrl_results.csv"
            if fields[6]["text"] in ("batch_dir_summary.csv",):
                fields[6]["text"] = "batch_ctrl_summary.csv"

    while confirmed is None:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return None
                if event.key == pygame.K_RETURN:
                    try:
                        cfg = {
                            "pheromones": parse_list(fields[0]["text"]),
                            "slipperiness": parse_list(fields[1]["text"]),
                            "replicates": int(fields[2]["text"]),
                            "jobs": int(fields[3]["text"]),
                            "base_seed": int(fields[4]["text"]),
                            "output": fields[5]["text"].strip() or "batch_results.csv",
                            "summary_output": fields[6]["text"].strip() or "batch_summary.csv",
                            "blue_directed": (directed_idx == 0),
                            "fresh_start": fresh_start,
                        }
                        ok, warns, errs = validate_cfg(cfg)
                        if not ok:
                            error_msg = " | ".join(errs)
                            warning_msg = ""
                        else:
                            confirmed = cfg
                            error_msg = ""
                            warning_msg = " | ".join(warns)
                    except Exception as e:
                        error_msg = f"Erro ao ler parametros: {e}"
                        warning_msg = ""
                    break
                if event.key in (pygame.K_TAB, pygame.K_DOWN):
                    active = (active + 1) % len(fields)
                elif event.key == pygame.K_UP:
                    active = (active - 1) % len(fields)
                elif event.key == pygame.K_BACKSPACE:
                    fields[active]["text"] = fields[active]["text"][:-1]
                else:
                    ch = event.unicode
                    if ch and ch.isprintable() and ch not in ("\t", "\r", "\n"):
                        fields[active]["text"] += ch
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for i in range(len(fields)):
                    if field_rect(i).collidepoint(mx, my):
                        active = i
                r1 = pygame.Rect(x_field, 120, 22, 22)
                r2 = pygame.Rect(x_field + 320, 120, 22, 22)
                if r1.collidepoint(mx, my):
                    directed_idx = 0
                    update_filename_if_default()
                elif r2.collidepoint(mx, my):
                    directed_idx = 1
                    update_filename_if_default()
                # Checkbox Fresh start
                cb = pygame.Rect(x_field, 170, 22, 22)
                if cb.collidepoint(mx, my):
                    fresh_start = not fresh_start

        if confirmed is not None:
            break

        screen.fill((12, 12, 18))

        title = font_title.render("Batch runner DS17 - parameters", True, (255, 255, 255))
        screen.blit(title, ((W - title.get_width()) // 2, 30))

        hint = font_small.render(
            "TAB/DOWN: next field.  ENTER: start.  ESC: quit.",
            True, (180, 180, 180))
        screen.blit(hint, ((W - hint.get_width()) // 2, 78))

        # Radio
        lbl = font_body.render("Blue directed:", True, (255, 255, 255))
        screen.blit(lbl, (x_label, 118))

        r1 = pygame.Rect(x_field, 120, 22, 22)
        pygame.draw.circle(screen, (220, 220, 220), r1.center, 11, 2)
        if directed_idx == 0:
            pygame.draw.circle(screen, (255, 255, 0), r1.center, 6)
        t1 = font_body.render("yes  (experiment)", True,
                              (255, 255, 255) if directed_idx == 0 else (200, 200, 200))
        screen.blit(t1, (r1.right + 10, r1.y - 2))

        r2 = pygame.Rect(x_field + 320, 120, 22, 22)
        pygame.draw.circle(screen, (220, 220, 220), r2.center, 11, 2)
        if directed_idx == 1:
            pygame.draw.circle(screen, (255, 255, 0), r2.center, 6)
        t2 = font_body.render("no  (control / null)", True,
                              (255, 255, 255) if directed_idx == 1 else (200, 200, 200))
        screen.blit(t2, (r2.right + 10, r2.y - 2))

        # Fresh start checkbox
        cb = pygame.Rect(x_field, 170, 22, 22)
        pygame.draw.rect(screen, (220, 220, 220), cb, 2, border_radius=3)
        if fresh_start:
            pygame.draw.line(screen, (255, 255, 0),
                             (cb.left + 4, cb.centery),
                             (cb.centerx - 2, cb.bottom - 6), 3)
            pygame.draw.line(screen, (255, 255, 0),
                             (cb.centerx - 2, cb.bottom - 6),
                             (cb.right - 4, cb.top + 4), 3)
        t3 = font_body.render("Fresh start (delete existing output CSV)",
                              True, (255, 255, 255))
        screen.blit(t3, (cb.right + 10, cb.y - 2))

        # Fields
        for i, f in enumerate(fields):
            col = (255, 255, 100) if i == active else (220, 220, 220)
            lbl = font_body.render(f["label"], True, col)
            screen.blit(lbl, (x_label, y0 + i * row_h + 6))

            r = field_rect(i)
            bg = (50, 50, 70) if i == active else (35, 35, 45)
            pygame.draw.rect(screen, bg, r, border_radius=4)
            pygame.draw.rect(screen,
                             (180, 180, 200) if i == active else (90, 90, 110),
                             r, 2, border_radius=4)
            txt_surf = font_body.render(f["text"], True, (255, 255, 255))
            screen.blit(txt_surf, (r.x + 8, r.y + 4))

            if i == active:
                cw = txt_surf.get_width()
                pygame.draw.line(screen, (255, 255, 100),
                                 (r.x + 8 + cw + 1, r.y + 4),
                                 (r.x + 8 + cw + 1, r.y + r.h - 6), 2)

        # Error/warning messages
        msg_y = y0 + len(fields) * row_h + 20
        if error_msg:
            err_surf = font_body.render("ERRO: " + error_msg, True, (255, 120, 120))
            screen.blit(err_surf, (x_label, msg_y))
            msg_y += 30
        if warning_msg:
            warn_surf = font_small.render("Aviso: " + warning_msg, True, (255, 220, 120))
            screen.blit(warn_surf, (x_label, msg_y))
            msg_y += 26

        # Notes
        note1 = font_small.render(
            "Limites: SLIP em [0.85, 1.00]  (recomendado >= 0.90).  "
            "PH em (0.05, 0.95).",
            True, (200, 200, 200))
        note2 = font_small.render(
            "O checkpoint DS17 usa (pheromone, friction, directed, replicate) "
            "como chave.",
            True, (180, 180, 180))
        note3 = font_small.render(
            "Pode rodar diferentes grids no mesmo CSV sem risco de dedup errada.",
            True, (180, 180, 180))
        screen.blit(note1, (x_label, msg_y + 10))
        screen.blit(note2, (x_label, msg_y + 32))
        screen.blit(note3, (x_label, msg_y + 54))

        pygame.display.flip()

    pygame.quit()
    return confirmed


# ============================================================================
# CLI
# ============================================================================
def build_parser():
    p = argparse.ArgumentParser(
        description="Batch runner paralelo para Insects_DS15.py (DS17)."
    )
    p.add_argument("--grid", default=None,
                   help="Grid file. Se omitido, abre a GUI.")
    p.add_argument("--output", default="batch_results.csv")
    p.add_argument("--summary-output", default="batch_summary.csv")
    p.add_argument("--seed-mode", choices=["random", "fixed"], default="fixed")
    p.add_argument("--base-seed", type=int, default=42)
    p.add_argument("--resume", action="store_true",
                   help="Se ativo, retoma de onde parou. Se desativado, "
                        "comporta-se como fresh start.")
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--yes", action="store_true",
                   help="Direcionamento azul ligado (experimento).")
    p.add_argument("--no", dest="control", action="store_true",
                   help="Direcionamento azul desligado (controle).")
    return p


def main():
    args = build_parser().parse_args()

    if args.grid:
        conditions = load_grid(args.grid)
        if not conditions:
            print("[main] grid vazio.", flush=True)
            return
        # Se CLI, mantem comportamento simples
        directed_set = set(c["blue_directed"] for c in conditions)
        if len(directed_set) > 1:
            print("[main] AVISO: grid MISTURA yes e no. "
                  "Recomendado rodar um modo por vez.", flush=True)
    else:
        cfg = gui_menu()
        if cfg is None:
            print("[main] GUI cancelada.", flush=True)
            return
        conditions = build_conditions_from_cfg(cfg)
        args.output = cfg["output"]
        args.summary_output = cfg["summary_output"]
        args.seed_mode = "fixed"
        args.base_seed = cfg["base_seed"]
        args.jobs = cfg["jobs"]
        args.resume = not cfg["fresh_start"]
        # Reporta avisos validados na GUI (ja validados)
        ok, warns, errs = validate_cfg(cfg)
        for w in warns:
            print(f"[main] AVISO: {w}", flush=True)

    total_replicates = sum(c["replicates"] for c in conditions)
    directed_all = set(c["blue_directed"] for c in conditions)
    if len(directed_all) == 1:
        mode_str = "yes (directed)" if directed_all.pop() else "no (control)"
    else:
        mode_str = "MIXED"

    print("=" * 72, flush=True)
    print(f"Insects batch (DS17) - modulo {sim.__file__}", flush=True)
    print("=" * 72, flush=True)
    print(f"Mode:             {mode_str}")
    print(f"Conditions:       {len(conditions)}")
    print(f"Total replicates: {total_replicates}")
    print(f"Seed mode:        {args.seed_mode}  (base_seed={args.base_seed})")
    print(f"Parallel jobs:    {args.jobs}")
    print(f"Output:           {args.output}")
    print(f"Summary:          {args.summary_output}")
    print(f"Resume:           {args.resume}")
    print("=" * 72, flush=True)

    # Fresh start: apaga arquivo se existir
    if not args.resume and os.path.exists(args.output):
        print(f"[fresh] Apagando {args.output} ...", flush=True)
        try:
            os.remove(args.output)
        except OSError as e:
            print(f"[fresh] AVISO: nao foi possivel apagar: {e}", flush=True)

    completed_rows = load_completed_results(args.output) if args.resume else []
    completed_keys = set()
    matched = 0
    for row in completed_rows:
        try:
            k = param_key(row["pheromone"], row["friction"],
                          row["blue_directed"], row["replicate"])
            completed_keys.add(k)
        except (KeyError, ValueError, TypeError):
            continue

    # Conta quantas replicas do grid atual ja tem no CSV
    for cond in conditions:
        ph = cond["pheromone"]; fr = cond["friction"]
        d = "yes" if cond["blue_directed"] else "no"
        for rep in range(1, cond["replicates"] + 1):
            if param_key(ph, fr, d, rep) in completed_keys:
                matched += 1

    print(f"Checkpoint total:      {len(completed_rows)} linhas no CSV.", flush=True)
    print(f"Checkpoint relevantes: {matched} replicas casam com este grid.", flush=True)
    print("=" * 72, flush=True)

    tasks = []
    for cond in conditions:
        ph, fr = cond["pheromone"], cond["friction"]
        directed = cond["blue_directed"]
        d_str = "yes" if directed else "no"
        mg = cond["max_generations"]
        for rep in range(1, cond["replicates"] + 1):
            if param_key(ph, fr, d_str, rep) in completed_keys:
                continue
            if args.seed_mode == "fixed":
                seed = stable_seed(args.base_seed, ph, fr, rep)
            else:
                seed = random.randrange(1, 2**63)
            # cond_id usado apenas para o log; nao e a chave de dedup
            cond_id = f"{ph:g}|{fr:g}|{d_str}"
            tasks.append((cond_id, rep, ph, fr, directed, seed, mg))

    print(f"Replicas a executar: {len(tasks)}", flush=True)
    print("=" * 72, flush=True)
    if not tasks:
        print("Nada a fazer. Gerando summary a partir do CSV existente.")
        summary = write_summary_csv(args.summary_output, completed_rows)
        _print_summary(summary)
        return

    all_rows = list(completed_rows)
    global_start = time.perf_counter()
    done = 0
    n_total = len(tasks)
    recent = []

    try:
        try:
            import joblib
            joblib_version = tuple(int(x) for x in joblib.__version__.split(".")[:2])
        except Exception:
            joblib_version = (1, 0)

        if joblib_version >= (1, 3):
            result_iter = Parallel(
                n_jobs=args.jobs,
                return_as="generator_unordered",
            )(delayed(_run_one_replicate)(*t) for t in tasks)

            for row in result_iter:
                append_result_csv(args.output, row)
                all_rows.append(row)
                done += 1
                recent.append(time.perf_counter())

                eta_str = ""
                if len(recent) >= 3:
                    span = recent[-1] - recent[max(0, len(recent) - 21)]
                    nr = min(len(recent) - 1, 20)
                    if span > 0 and nr > 0:
                        rate = nr / span
                        eta = (n_total - done) / rate if rate > 0 else 0
                        eta_str = f"  ETA ~{eta/60:.1f} min"

                flag = row["fixed_color"] or "no-fix"
                print(f"[{done:>4}/{n_total}] "
                      f"cond={row['condition_id']:<12} rep={row['replicate']:>3} "
                      f"PH={row['pheromone']:g} SLIP={row['friction']:g} "
                      f"dir={row['blue_directed']:<3} -> {flag} "
                      f"gen={row['fixation_generation']} "
                      f"({row['runtime_seconds']}s){eta_str}",
                      flush=True)
        else:
            print("[warn] joblib < 1.3 - checkpoint incremental desativado.")
            results = Parallel(n_jobs=args.jobs)(
                delayed(_run_one_replicate)(*t) for t in tasks
            )
            for row in results:
                append_result_csv(args.output, row)
                all_rows.append(row)
                done += 1
                print(f"[{done:>4}/{n_total}] {row['fixed_color']}", flush=True)

    except KeyboardInterrupt:
        print("\n[interrupt] Ctrl+C recebido. Use resume (sem Fresh start) "
              "para continuar.", flush=True)

    summary = write_summary_csv(args.summary_output, all_rows)
    elapsed = time.perf_counter() - global_start
    print()
    print("=" * 72)
    print("DONE")
    print(f"Replicas no arquivo: {len(all_rows)}")
    print(f"Tempo total:         {elapsed:.1f} s ({elapsed/60:.1f} min)")
    print(f"Results:             {args.output}")
    print(f"Summary:             {args.summary_output}")
    _print_summary(summary)
    print("=" * 72)


def _print_summary(summary):
    if not summary:
        return
    print("-" * 72)
    print(f"{'cid':>4}  {'PH':>5}  {'SLIP':>5}  {'dir':>3}  "
          f"{'n':>4}  {'blue':>5}  {'red':>4}  {'blue_frac':>9}")
    for s in summary:
        print(f"{s['condition_id']:>4}  {s['pheromone']:>5g}  {s['friction']:>5g}  "
              f"{s['blue_directed']:>3}  {s['n_replicates']:>4}  "
              f"{s['n_blue']:>5}  {s['n_red']:>4}  {s['blue_fraction']:>9}")


if __name__ == "__main__":
    main()