# roguelike.py — ASCII Roguelike (curses) with XP + Depth
# Runs in a terminal. Windows users: pip install windows-curses

import math
import os
import random
import sys
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Set

# ---- Optional: load curses shim on Windows ----
try:
    import curses
except Exception as e:  # pragma: no cover
    print("Curses not available. On Windows run:\n  python -m pip install windows-curses")
    raise

# --------------- Config ---------------
MAP_W, MAP_H = 60, 28
PANEL_W = 30
SCREEN_W, SCREEN_H = MAP_W + PANEL_W, MAP_H + 2
FOV_RADIUS = 8
ROOM_MIN, ROOM_MAX = 4, 9
MAX_ROOMS = 12
LOG_MAX = 120

# Tiles
WALL, FLOOR, STAIRS, POTION = '#', '.', '>', '!'
PLAYER_GLYPH = 'S'

# Enemy templates
ENEMIES: Dict[str, Dict] = {
    "goblin": {"ch": "g", "hp": 5, "atk": 8,  "dmg": (1, 2), "ai": "melee",  "speed": 1, "xp": 8},
    "orc":    {"ch": "o", "hp": 10, "atk": 10, "dmg": (2, 3), "ai": "melee",  "speed": 1, "xp": 14},
    "wolf":   {"ch": "w", "hp": 6,  "atk": 9,  "dmg": (1, 2), "ai": "runner", "speed": 2, "xp": 10},
    "archer": {"ch": "a", "hp": 6,  "atk": 8,  "dmg": (1, 2), "ai": "ranged", "speed": 1, "range": 7, "prefer": 4, "xp": 12},
    "troll":  {"ch": "T", "hp": 20, "atk": 10, "dmg": (3, 5), "ai": "melee",  "speed": 1, "regen": 1, "xp": 24},
}

# DSA-ish attributes (very lightweight placeholders)
ATTRS = ["MU", "KL", "IN", "CH", "FF", "GE", "KO", "KK"]
RACE_DWARF = {"KO": +2, "KK": +2, "GE": -1, "CH": -1}
PROF_SLAYER = {"KK": +2, "MU": +1}

# --------------- Data ---------------
@dataclass
class Entity:
    x: int
    y: int
    ch: str
    name: str
    hp: int
    max_hp: int
    alive: bool = True
    fresh: bool = True
    ai: str = "melee"
    atk: int = 8
    dmg: Tuple[int, int] = (1, 2)
    speed: int = 1
    regen: int = 0
    range: int = 0
    prefer: int = 0
    xp: int = 0

@dataclass
class Player:
    x: int
    y: int
    attrs: Dict[str, int]
    atk: int
    par: int
    max_hp: int
    hp: int
    potions: int = 0
    level: int = 1
    xp: int = 0
    next_xp: int = 0

@dataclass
class Game:
    depth: int
    turn: int
    grid: List[List[str]]
    rooms: List[Tuple[int, int, int, int]]
    player: Player
    mobs: List[Entity]
    items: List[Tuple[int, int, str]]  # (x,y,type) type: 'potion'
    stairs: Tuple[int, int]
    explored: Set[Tuple[int, int]] = field(default_factory=set)
    log: List[str] = field(default_factory=lambda: ["You shoulder your axe and enter."])
    over: bool = False

# --------------- RNG helpers ---------------
def roll(n: int, s: int) -> int:
    return sum(random.randint(1, s) for _ in range(n))

def rint(a: int, b: int) -> int:
    return random.randint(a, b)

# --------------- Map gen ---------------
def rect(x, y, w, h): return (x, y, w, h)
def center(r): x, y, w, h = r; return (x + w // 2, y + h // 2)

def carve_room(grid, r):
    x, y, w, h = r
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            grid[yy][xx] = FLOOR

def carve_h(grid, x1, x2, y):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        grid[y][x] = FLOOR

def carve_v(grid, y1, y2, x):
    for y in range(min(y1, y2), max(y1, y2) + 1):
        grid[y][x] = FLOOR

def make_map() -> Tuple[List[List[str]], List[Tuple[int,int,int,int]]]:
    grid = [[WALL for _ in range(MAP_W)] for _ in range(MAP_H)]
    rooms = []
    for _ in range(MAX_ROOMS):
        w, h = rint(ROOM_MIN, ROOM_MAX), rint(ROOM_MIN, ROOM_MAX)
        x = rint(1, MAP_W - w - 2)
        y = rint(1, MAP_H - h - 2)
        new = rect(x, y, w, h)
        overlaps = any(x <= ox + ow and x + w >= ox and y <= oy + oh and y + h >= oy
                       for ox, oy, ow, oh in rooms)
        if overlaps: 
            continue
        carve_room(grid, new)
        if rooms:
            ax, ay = center(rooms[-1])
            bx, by = center(new)
            if random.random() < 0.5:
                carve_h(grid, ax, bx, ay); carve_v(grid, ay, by, bx)
            else:
                carve_v(grid, ay, by, ax); carve_h(grid, ax, bx, by)
        rooms.append(new)
    return grid, rooms

# --------------- LOS / FOV ---------------
def bresenham_line(x0, y0, x1, y1):
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx - dy
    x, y = x0, y0
    while True:
        yield x, y
        if x == x1 and y == y1: break
        e2 = 2 * err
        if e2 > -dy: err -= dy; x += sx
        if e2 <  dx: err += dx; y += sy

def in_bounds(x, y): return 0 <= x < MAP_W and 0 <= y < MAP_H

def los_clear(grid, x0, y0, x1, y1):
    for i, (x, y) in enumerate(bresenham_line(x0, y0, x1, y1)):
        if i == 0: 
            continue
        if not in_bounds(x, y): 
            return False
        if grid[y][x] == WALL and not (x == x1 and y == y1):
            return False
    return True

def fov(player: Player, grid) -> Set[Tuple[int,int]]:
    out = set()
    for y in range(max(0, player.y - FOV_RADIUS), min(MAP_H, player.y + FOV_RADIUS + 1)):
        for x in range(max(0, player.x - FOV_RADIUS), min(MAP_W, player.x + FOV_RADIUS + 1)):
            if (x - player.x) ** 2 + (y - player.y) ** 2 <= FOV_RADIUS ** 2:
                if los_clear(grid, player.x, player.y, x, y):
                    out.add((x, y))
    return out

# --------------- DSA-ish derived stats ---------------
def roll_base_attrs() -> Dict[str,int]:
    base = {a: rint(8, 14) for a in ATTRS}
    for k, v in RACE_DWARF.items(): base[k] = base.get(k, 10) + v
    for k, v in PROF_SLAYER.items(): base[k] = base.get(k, 10) + v
    return base

def derive(attrs: Dict[str,int]) -> Tuple[int,int,int]:
    max_hp = 20 + max(0, attrs["KO"] - 10) + attrs["KK"] // 5
    atk = 6 + (attrs["KK"] + attrs["GE"]) // 4
    par = 4 + (attrs["GE"] + attrs["MU"]) // 5
    return max_hp, atk, par

def xp_threshold(level: int) -> int:
    return 20 + level * 10

# --------------- Spawns ---------------
def depth_spawn_bag(depth: int) -> List[str]:
    bag = []
    def push(name, w):
        bag.extend([name] * max(0, w))
    push("goblin", max(2, 8 - min(depth, 6)))
    push("wolf", max(1, depth))
    push("archer", max(1, depth // 1))
    push("orc", max(1, 1 + depth // 2))
    if depth >= 2:
        push("troll", max(1, depth - 1))
    return bag or ["goblin"]

def spawn_mobs_items(g: Game):
    # player start and stairs
    start = center(g.rooms[0])
    end   = center(g.rooms[-1])
    g.player.x, g.player.y = start
    g.stairs = end

    # items
    for _ in range(7):
        while True:
            x, y = rint(1, MAP_W-2), rint(1, MAP_H-2)
            if g.grid[y][x] == FLOOR and (x, y) not in [start, end]:
                g.items.append((x, y, "potion")); break

    # enemies
    bag = depth_spawn_bag(g.depth)
    for _ in range(12):
        while True:
            x, y = rint(1, MAP_W-2), rint(1, MAP_H-2)
            if g.grid[y][x] == FLOOR and (x, y) not in [start, end]:
                kind = random.choice(bag)
                t = ENEMIES[kind]
                g.mobs.append(Entity(x, y, t["ch"], kind, t["hp"], t["hp"], True, True,
                                     t["ai"], t["atk"], t["dmg"], t.get("speed",1),
                                     t.get("regen",0), t.get("range",0), t.get("prefer",0),
                                     t.get("xp",8)))
                break

# --------------- Combat / AI ---------------
def push_log(g: Game, msg: str):
    g.log.append(msg)
    if len(g.log) > LOG_MAX:
        g.log = g.log[-LOG_MAX:]

def damage_roll(dmg: Tuple[int,int]) -> int:
    a, b = dmg
    return random.randint(a, b)

def player_attack(g: Game, mob: Entity):
    if roll(1,20) <= max(3, g.player.atk - 2):
        opener = roll(1,2) if mob.fresh else 0
        mob.fresh = False
        base = 2 + roll(1,3)
        kk_bonus = max(0, (g.player.attrs["KK"] - 10) // 2)
        dmg = max(1, base + kk_bonus + opener)
        mob.hp -= dmg
        push_log(g, f"You hit the {mob.name} for {dmg}.")
        if mob.hp <= 0:
            mob.alive = False
            push_log(g, f"{mob.name.capitalize()} dies!")
            award_xp(g, mob.xp)
    else:
        push_log(g, f"You miss the {mob.name}.")

def award_xp(g: Game, amount: int):
    g.player.xp += amount
    push_log(g, f"You gain {amount} XP.")
    while g.player.xp >= g.player.next_xp:
        g.player.xp -= g.player.next_xp
        g.player.level += 1
        g.player.next_xp = xp_threshold(g.player.level)
        g.player.max_hp += 4
        g.player.atk += 1
        if g.player.level % 2 == 0:
            g.player.par += 1
        g.player.hp = min(g.player.max_hp, g.player.hp + 4)
        push_log(g, f"*** Level Up! Level {g.player.level}. MaxHP+4, AT+1{', PA+1' if g.player.level % 2 == 0 else ''}.")

def enemy_attack_player(g: Game, m: Entity):
    if roll(1,20) <= m.atk and roll(1,20) > g.player.par:
        dmg = damage_roll(m.dmg)
        g.player.hp -= dmg
        push_log(g, f"{m.name.capitalize()} hits you ({dmg}).")
    else:
        push_log(g, f"You fend off the {m.name}.")

def step_toward(g: Game, m: Entity, tx: int, ty: int):
    dx = (1 if tx > m.x else -1 if tx < m.x else 0)
    dy = (1 if ty > m.y else -1 if ty < m.y else 0)
    nx, ny = m.x + dx, m.y + dy
    if not in_bounds(nx, ny): 
        return
    if g.grid[ny][nx] == WALL: 
        return
    if (nx, ny) == (g.player.x, g.player.y): 
        return
    if any(o.alive and (o.x, o.y) == (nx, ny) and o is not m for o in g.mobs): 
        return
    m.x, m.y = nx, ny

def ai_turn(g: Game):
    for m in g.mobs:
        if not m.alive:
            continue

        # Troll regen
        if m.regen and m.hp > 0 and m.hp < m.max_hp:
            m.hp = min(m.max_hp, m.hp + m.regen)

        dist = math.hypot(m.x - g.player.x, m.y - g.player.y)

        if m.ai == "ranged":
            if dist > 1 and dist <= m.range and los_clear(g.grid, m.x, m.y, g.player.x, g.player.y):
                enemy_attack_player(g, m)
                continue
            if dist < m.prefer:
                step_toward(g, m, m.x - (g.player.x - m.x), m.y - (g.player.y - m.y))
            else:
                step_toward(g, m, g.player.x, g.player.y)
            continue

        # melee/runner
        steps = 2 if (m.ai == "runner" and dist > 2) else 1
        for _ in range(steps):
            if dist <= 1.5:
                enemy_attack_player(g, m)
                break
            step_toward(g, m, g.player.x, g.player.y)
            dist = math.hypot(m.x - g.player.x, m.y - g.player.y)

# --------------- Movement ---------------
def try_move_player(g: Game, dx: int, dy: int):
    nx, ny = max(0, min(MAP_W - 1, g.player.x + dx)), max(0, min(MAP_H - 1, g.player.y + dy))
    if g.grid[ny][nx] == WALL:
        return
    # attack?
    for m in g.mobs:
        if m.alive and (m.x, m.y) == (nx, ny):
            player_attack(g, m)
            return
    # move
    g.player.x, g.player.y = nx, ny

    # pickup
    for i, (ix, iy, typ) in enumerate(list(g.items)):
        if (ix, iy) == (g.player.x, g.player.y) and typ == "potion":
            g.player.potions += 1
            g.items.pop(i)
            push_log(g, "You pick up a healing draught.")
            break

    # stairs
    if (g.player.x, g.player.y) == g.stairs:
        g.depth += 1
        g.turn += 1
        push_log(g, f"You descend to Depth {g.depth}.")
        new_floor(g)

def use_potion(g: Game):
    if g.player.potions <= 0:
        return
    g.player.potions -= 1
    heal = max(4, 6 + max(0, (g.player.attrs["KO"] - 10) // 2))
    g.player.hp = min(g.player.max_hp, g.player.hp + heal)
    push_log(g, "You quaff a bitter dwarf brew. (+HP)")

# --------------- Floor reset ---------------
def new_floor(g: Game = None) -> Game:
    # Create or rebuild
    grid, rooms = make_map()
    if g is None:
        attrs = roll_base_attrs()
        max_hp, atk, par = derive(attrs)
        p = Player(1, 1, attrs, atk, par, max_hp, max_hp, 0, 1, 0, xp_threshold(1))
        g = Game(1, 1, grid, rooms, p, [], [], (0,0), set(), ["You shoulder your axe and enter."], False)
        spawn_mobs_items(g)
        return g

    # Reuse player
    g.grid, g.rooms, g.mobs, g.items, g.explored = grid, rooms, [], [], set()
    spawn_mobs_items(g)
    return g

# --------------- Drawing ---------------
def draw(stdscr, g: Game):
    stdscr.erase()
    # Map
    vis = fov(g.player, g.grid)
    for vx, vy in vis:
        g.explored.add((vx, vy))
    for y in range(MAP_H):
        for x in range(MAP_W):
            ch = g.grid[y][x]
            if (x, y) == g.stairs: ch = STAIRS
            for m in g.mobs:
                if m.alive and (m.x, m.y) == (x, y):
                    ch = ENEMIES[m.name]["ch"]
                    break
            if (g.player.x, g.player.y) == (x, y):
                ch = PLAYER_GLYPH
            if (x, y) in g.explored:
                attr = curses.A_BOLD if (x, y) in vis else curses.A_DIM
                stdscr.addch(y, x, ch, attr)
            else:
                stdscr.addch(y, x, ord(' '))

    # Panel
    px = MAP_W + 1
    def put(y, text, attr=0):
        stdscr.addstr(y, px, text.ljust(PANEL_W - 1)[:PANEL_W - 1], attr)

    put(0, f"Dwarf Slayer — Depth {g.depth}", curses.A_BOLD)
    put(1, f"HP {g.player.hp}/{g.player.max_hp}   Turn {g.turn}")
    put(2, f"Lvl {g.player.level}   XP {g.player.xp}/{g.player.next_xp}")
    put(3, f"AT {g.player.atk}  PA {g.player.par}")
    put(4, f"Potions: {g.player.potions}")
    put(5, "-" * (PANEL_W - 2))
    put(6, "Saga Log (newest first):", curses.A_BOLD)

    # Newest first
    log_lines = list(reversed(g.log))[:MAP_H - 9]
    for i, line in enumerate(log_lines, start=7):
        put(i, f"• {line}")

    put(MAP_H - 1, "[Arrows/WASD] Move  [.] Wait  [R] Rest  [P] Potion  [Q] Quit")

    stdscr.refresh()

# --------------- Game loop ---------------
def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.timeout(0)  # non-blocking getch; we’ll do a tiny sleep

    random.seed()  # system entropy

    g = new_floor(None)

    while True:
        draw(stdscr, g)
        if g.over:
            stdscr.getch()
            return

        # Input
        ch = stdscr.getch()
        if ch == -1:
            curses.napms(10)
            continue

        key = chr(ch).lower() if 0 <= ch < 256 else None
        dx = dy = 0
        if ch in (curses.KEY_UP,) or key == 'w': dy = -1
        elif ch in (curses.KEY_DOWN,) or key == 's': dy = +1
        elif ch in (curses.KEY_LEFT,) or key == 'a': dx = -1
        elif ch in (curses.KEY_RIGHT,) or key == 'd': dx = +1
        elif key == '.': dx = dy = 0  # wait
        elif key == 'r': 
            g.player.hp = min(g.player.max_hp, g.player.hp + 1)
            push_log(g, "You catch your breath.")
            g.turn += 1
            ai_turn(g)
            continue
        elif key == 'p':
            use_potion(g)
            g.turn += 1
            ai_turn(g)
            continue
        elif key == 'q':
            break
        else:
            continue  # ignore unknown keys

        # Move/act
        try_move_player(g, dx, dy)
        g.turn += 1
        ai_turn(g)
        if g.player.hp <= 0:
            g.over = True
            push_log(g, "You fall...")

if __name__ == "__main__":
    curses.wrapper(main)
