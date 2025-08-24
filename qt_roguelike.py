# qt_roguelike.py — PyQt6 GUI Roguelike (XP + Depth + FOV + Multiple Enemies)
# Adds: visible potions + tile renderer (toggle ASCII/Tiles with T)
# Install:  python -m pip install PyQt6

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Set

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QSplitter, QTabWidget
)

# -------------------------
# CONFIG / CONSTANTS
# -------------------------
MAP_W, MAP_H = 60, 28
FOV_RADIUS = 8
ROOM_MIN, ROOM_MAX = 4, 9
MAX_ROOMS = 12
LOG_MAX = 160

WALL, FLOOR, STAIRS, POTION = '#', '.', '>', '!'
PLAYER_GLYPH = 'S'

ENEMIES: Dict[str, Dict] = {
    "goblin": {"ch": "g", "hp": 5,  "atk": 8,  "dmg": (1, 2), "ai": "melee",  "speed": 1, "xp": 8},
    "orc":    {"ch": "o", "hp": 10, "atk": 10, "dmg": (2, 3), "ai": "melee",  "speed": 1, "xp": 14},
    "wolf":   {"ch": "w", "hp": 6,  "atk": 9,  "dmg": (1, 2), "ai": "runner", "speed": 2, "xp": 10},
    "archer": {"ch": "a", "hp": 6,  "atk": 8,  "dmg": (1, 2), "ai": "ranged", "speed": 1, "range": 7, "prefer": 4, "xp": 12},
    "troll":  {"ch": "T", "hp": 20, "atk": 10, "dmg": (3, 5), "ai": "melee",  "speed": 1, "regen": 1, "xp": 24},
}

ATTRS = ["MU", "KL", "IN", "CH", "FF", "GE", "KO", "KK"]
RACE_DWARF = {"KO": +2, "KK": +2, "GE": -1, "CH": -1}
PROF_SLAYER = {"KK": +2, "MU": +1}


# -------------------------
# DATA STRUCTURES (MODEL)
# -------------------------
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
    items: List[Tuple[int, int, str]]  # (x,y,'potion')
    stairs: Tuple[int, int]
    explored: Set[Tuple[int, int]] = field(default_factory=set)
    log: List[str] = field(default_factory=lambda: ["You shoulder your axe and enter."])
    over: bool = False


# -------------------------
# UTILS / RNG / MAP
# -------------------------
def roll(n: int, s: int) -> int:
    return sum(random.randint(1, s) for _ in range(n))


def rint(a: int, b: int) -> int:
    return random.randint(a, b)


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


def make_map():
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


# -------------------------
# LOS / FOV
# -------------------------
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


def fov(player: Player, grid) -> Set[Tuple[int, int]]:
    out = set()
    for y in range(max(0, player.y - FOV_RADIUS), min(MAP_H, player.y + FOV_RADIUS + 1)):
        for x in range(max(0, player.x - FOV_RADIUS), min(MAP_W, player.x + FOV_RADIUS + 1)):
            if (x - player.x) ** 2 + (y - player.y) ** 2 <= FOV_RADIUS ** 2:
                if los_clear(grid, player.x, player.y, x, y):
                    out.add((x, y))
    return out


# -------------------------
# DSA-ish DERIVED STATS
# -------------------------
def roll_base_attrs() -> Dict[str, int]:
    base = {a: rint(8, 14) for a in ATTRS}
    for k, v in RACE_DWARF.items(): base[k] = base.get(k, 10) + v
    for k, v in PROF_SLAYER.items(): base[k] = base.get(k, 10) + v
    return base


def derive(attrs: Dict[str, int]):
    max_hp = 20 + max(0, attrs["KO"] - 10) + attrs["KK"] // 5
    atk = 6 + (attrs["KK"] + attrs["GE"]) // 4
    par = 4 + (attrs["GE"] + attrs["MU"]) // 5
    return max_hp, atk, par


def xp_threshold(level: int) -> int:
    return 20 + level * 10


# -------------------------
# SPAWNS
# -------------------------
def depth_spawn_bag(depth: int) -> List[str]:
    bag = []
    def push(name, w): bag.extend([name] * max(0, w))
    push("goblin", max(2, 8 - min(depth, 6)))
    push("wolf", max(1, depth))
    push("archer", max(1, depth // 1))
    push("orc", max(1, 1 + depth // 2))
    if depth >= 2:
        push("troll", max(1, depth - 1))
    return bag or ["goblin"]


def spawn_mobs_items(g: Game):
    start = center(g.rooms[0]); end = center(g.rooms[-1])
    g.player.x, g.player.y = start
    g.stairs = end

    # items (potions)
    for _ in range(7):
        for _tries in range(200):
            x, y = rint(1, MAP_W - 2), rint(1, MAP_H - 2)
            if g.grid[y][x] == FLOOR and (x, y) not in [start, end]:
                g.items.append((x, y, "potion")); break

    # enemies
    bag = depth_spawn_bag(g.depth)
    for _ in range(12):
        for _tries in range(300):
            x, y = rint(1, MAP_W - 2), rint(1, MAP_H - 2)
            if g.grid[y][x] == FLOOR and (x, y) not in [start, end]:
                kind = random.choice(bag)
                t = ENEMIES[kind]
                g.mobs.append(Entity(x, y, t["ch"], kind, t["hp"], t["hp"], True, True,
                                     t["ai"], t["atk"], t["dmg"], t.get("speed", 1),
                                     t.get("regen", 0), t.get("range", 0), t.get("prefer", 0),
                                     t.get("xp", 8)))
                break


# -------------------------
# COMBAT / AI
# -------------------------
def push_log(g: Game, msg: str):
    g.log.append(msg)
    if len(g.log) > LOG_MAX:
        g.log = g.log[-LOG_MAX:]


def damage_roll(dmg: Tuple[int, int]) -> int:
    a, b = dmg
    return random.randint(a, b)


def player_attack(g: Game, mob: Entity):
    if roll(1, 20) <= max(3, g.player.atk - 2):
        opener = roll(1, 2) if mob.fresh else 0
        mob.fresh = False
        base = 2 + roll(1, 3)
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
    if roll(1, 20) <= m.atk and roll(1, 20) > g.player.par:
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

        steps = 2 if (m.ai == "runner" and dist > 2) else 1
        for _ in range(steps):
            if math.hypot(m.x - g.player.x, m.y - g.player.y) <= 1.5:
                enemy_attack_player(g, m)
                break
            step_toward(g, m, g.player.x, g.player.y)


# -------------------------
# PLAYER ACTIONS / FLOORS
# -------------------------
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


def new_floor(g: Game = None) -> Game:
    grid, rooms = make_map()
    if g is None:
        attrs = roll_base_attrs()
        max_hp, atk, par = derive(attrs)
        p = Player(1, 1, attrs, atk, par, max_hp, max_hp, 0, 1, 0, xp_threshold(1))
        g = Game(1, 1, grid, rooms, p, [], [], (0, 0), set(), ["You shoulder your axe and enter."], False)
        spawn_mobs_items(g)
        return g
    g.grid, g.rooms, g.mobs, g.items, g.explored = grid, rooms, [], [], set()
    spawn_mobs_items(g)
    return g


# -------------------------
# GUI WIDGETS
# -------------------------
class MapWidget(QWidget):
    """
    Paints the map & actors. Supports ASCII and tile modes (toggle with T).
    """
    def __init__(self, game: Game, parent=None):
        super().__init__(parent)
        self.game = game
        self.font = QFont("Courier New", 13)
        self.tile_w = 18
        self.tile_h = 18
        self.use_tiles = True  # default to tiles
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:
        return QSize(self.tile_w * MAP_W + 2, self.tile_h * MAP_H + 2)

    def setGame(self, g: Game):
        self.game = g
        self.update()

    def toggleTiles(self):
        self.use_tiles = not self.use_tiles
        self.update()

    # --------- TILE PAINTERS ----------
    def draw_floor(self, p, x, y, in_vis):
        px, py = x * self.tile_w, y * self.tile_h
        p.fillRect(px, py, self.tile_w, self.tile_h, QColor("#f1f5f9" if in_vis else "#e5e7eb"))

    def draw_wall(self, p, x, y, in_vis):
        px, py = x * self.tile_w, y * self.tile_h
        base = QColor("#94a3b8" if in_vis else "#cbd5e1")
        p.fillRect(px, py, self.tile_w, self.tile_h, base)
        # simple brick lines
        p.setPen(QPen(QColor("#64748b" if in_vis else "#94a3b8"), 1))
        p.drawLine(px, py + self.tile_h//2, px + self.tile_w, py + self.tile_h//2)
        p.drawLine(px + self.tile_w//3, py, px + self.tile_w//3, py + self.tile_h//2)
        p.drawLine(px + 2*self.tile_w//3, py + self.tile_h//2, px + 2*self.tile_w//3, py + self.tile_h)

    def draw_stairs(self, p, x, y, in_vis):
        px, py = x * self.tile_w, y * self.tile_h
        self.draw_floor(p, x, y, in_vis)
        p.setBrush(QBrush(QColor("#06b6d4")))
        p.setPen(Qt.PenStyle.NoPen)
        # little chevron
        m = 4
        p.drawPolygon(
            *[ (px+m,py+m), (px+self.tile_w-m,py+m), (px+self.tile_w-2*m,py+2*m),
               (px+2*m,py+2*m) ]
        )

    def draw_potion(self, p, x, y, in_vis):
        px, py = x * self.tile_w, y * self.tile_h
        self.draw_floor(p, x, y, in_vis)
        # flask
        body = QColor("#a855f7")  # purple
        glass = QColor("#ede9fe")
        neck = QColor("#7c3aed")
        p.setPen(Qt.PenStyle.NoPen)
        # bulb
        p.setBrush(QBrush(body))
        r = min(self.tile_w, self.tile_h) // 2 - 3
        p.drawEllipse(px + self.tile_w//2 - r, py + self.tile_h//2 - r + 2, 2*r, 2*r)
        # neck
        p.setBrush(QBrush(neck))
        p.drawRect(px + self.tile_w//2 - 3, py + 3, 6, 6)
        # highlight
        p.setBrush(QBrush(glass))
        p.drawEllipse(px + self.tile_w//2, py + self.tile_h//2 - 2, 5, 5)

    def draw_enemy(self, p, x, y, kind, in_vis):
        px, py = x * self.tile_w, y * self.tile_h
        self.draw_floor(p, x, y, in_vis)
        color = {"goblin":"#22c55e","orc":"#16a34a","wolf":"#111827","archer":"#ef4444","troll":"#dc2626"}.get(kind,"#ef4444")
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(px+3, py+3, self.tile_w-6, self.tile_h-6)
        # glyph
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(px+4, py+self.tile_h-5, ENEMIES[kind]["ch"])

    def draw_player(self, p, x, y, in_vis):
        px, py = x * self.tile_w, y * self.tile_h
        self.draw_floor(p, x, y, in_vis)
        p.setBrush(QBrush(QColor("#f59e0b")))
        p.setPen(Qt.PenStyle.NoPen)
        r = min(self.tile_w, self.tile_h)//2 - 2
        p.drawEllipse(px + self.tile_w//2 - r, py + self.tile_h//2 - r, 2*r, 2*r)
        # small axe slash accent
        p.setPen(QPen(QColor("#78350f"), 2))
        p.drawLine(px + self.tile_w//2, py + self.tile_h//2, px + self.tile_w//2 + 6, py + self.tile_h//2 - 6)

    # --------- PAINT ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setFont(self.font)
        fm = p.fontMetrics()
        # Keep a sensible minimum size from font
        self.tile_w = max(self.tile_w, fm.horizontalAdvance("M"))
        self.tile_h = max(self.tile_h, fm.height())

        g = self.game
        vis = fov(g.player, g.grid)
        for vx, vy in vis:
            g.explored.add((vx, vy))

        if self.use_tiles:
            # TILE MODE
            for y in range(MAP_H):
                for x in range(MAP_W):
                    in_vis = (x, y) in vis
                    ch = g.grid[y][x]
                    if ch == WALL:
                        self.draw_wall(p, x, y, in_vis)
                    else:
                        self.draw_floor(p, x, y, in_vis)

            # items (POTIONS) — draw before mobs/player so they can be covered if occupied
            for (ix, iy, typ) in g.items:
                if (ix, iy) in g.explored:
                    if typ == "potion":
                        self.draw_potion(p, ix, iy, (ix, iy) in vis)

            # stairs
            sx, sy = g.stairs
            if (sx, sy) in g.explored:
                self.draw_stairs(p, sx, sy, (sx, sy) in vis)

            # mobs
            for m in g.mobs:
                if not m.alive: continue
                if (m.x, m.y) in g.explored:
                    self.draw_enemy(p, m.x, m.y, m.name, (m.x, m.y) in vis)

            # player
            self.draw_player(p, g.player.x, g.player.y, True)

        else:
            # ASCII MODE (original)
            def draw_cell(x, y, ch, in_vis, exp):
                px = x * self.tile_w; py = y * self.tile_h
                bg = QColor("#f1f5f9") if in_vis else QColor("#e5e7eb") if exp else QColor("#ffffff")
                p.fillRect(px, py, self.tile_w, self.tile_h, bg)
                if exp:
                    fg = QColor("#111827") if in_vis else QColor("#6b7280")
                    p.setPen(fg)
                    p.drawText(px, py + fm.ascent() + (self.tile_h - fm.height())//2, ch)

            # base map
            for y in range(MAP_H):
                for x in range(MAP_W):
                    ch = g.grid[y][x]
                    if (x, y) == g.stairs: ch = STAIRS
                    # overlay: items
                    for it in g.items:
                        if (it[0], it[1]) == (x, y):
                            ch = '!'  # potion
                    # overlay: mobs
                    for m in g.mobs:
                        if m.alive and (m.x, m.y) == (x, y):
                            ch = ENEMIES[m.name]["ch"]; break
                    if (g.player.x, g.player.y) == (x, y):
                        ch = PLAYER_GLYPH
                    draw_cell(x, y, ch, (x, y) in vis, (x, y) in g.explored)

        p.end()


class StatsPanel(QWidget):
    def __init__(self, game: Game, parent=None):
        super().__init__(parent)
        self.game = game

        self.title = QLabel()
        self.stats1 = QLabel()
        self.stats2 = QLabel()
        self.stats3 = QLabel()

        for lbl in (self.title, self.stats1, self.stats2, self.stats3):
            lbl.setStyleSheet("font-family: Consolas, 'Courier New', monospace;")

        btn_row = QHBoxLayout()
        self.btn_rest = QPushButton("Rest (R)")
        self.btn_potion = QPushButton("Potion (P)")
        self.btn_new = QPushButton("New (N)")
        self.btn_toggle = QPushButton("Tiles ⟷ ASCII (T)")
        btn_row.addWidget(self.btn_rest)
        btn_row.addWidget(self.btn_potion)
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_toggle)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.stats1)
        layout.addWidget(self.stats2)
        layout.addWidget(self.stats3)
        layout.addSpacing(8)
        layout.addLayout(btn_row)
        layout.addStretch(1)

        self.updateFromGame(game)

    def updateFromGame(self, g: Game):
        self.title.setText(f"<b>Dwarf Slayer — Depth {g.depth}</b>")
        self.stats1.setText(f"HP {g.player.hp}/{g.player.max_hp}    Turn {g.turn}")
        self.stats2.setText(f"Lvl {g.player.level}    XP {g.player.xp}/{g.player.next_xp}")
        self.stats3.setText(f"AT {g.player.atk}   PA {g.player.par}")


class LogPanel(QPlainTextEdit):
    def __init__(self, game: Game, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("font-family: Consolas, 'Courier New', monospace;")
        self.updateFromGame(game)

    def updateFromGame(self, g: Game):
        newest_first = list(reversed(g.log))[:200]
        self.setPlainText("\n".join(f"• {line}" for line in newest_first))


# -------------------------
# MAIN WINDOW
# -------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASCII Roguelike — PyQt")

        self.game: Game = new_floor(None)

        # central splitter
        self.map_widget = MapWidget(self.game)
        self.side_tabs = QTabWidget()

        self.stats_panel = StatsPanel(self.game)
        self.log_panel = LogPanel(self.game)

        self.side_tabs.addTab(self.stats_panel, "Stats")
        self.side_tabs.addTab(self.log_panel, "Log")

        split = QSplitter()
        split.addWidget(self.map_widget)
        split.addWidget(self.side_tabs)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)

        # wrap in central widget
        cw = QWidget()
        lay = QHBoxLayout(cw)
        lay.addWidget(split)
        self.setCentralWidget(cw)

        # hook buttons
        self.stats_panel.btn_rest.clicked.connect(self.on_rest)
        self.stats_panel.btn_potion.clicked.connect(self.on_potion)
        self.stats_panel.btn_new.clicked.connect(self.on_new)
        self.stats_panel.btn_toggle.clicked.connect(self.on_toggle)

        self.resize(1120, 680)
        self.map_widget.setFocus()

    # ---- helpers ----
    def refresh(self):
        self.map_widget.update()
        self.stats_panel.updateFromGame(self.game)
        self.log_panel.updateFromGame(self.game)

    def end_turn(self):
        self.game.turn += 1
        ai_turn(self.game)
        if self.game.player.hp <= 0:
            self.game.over = True
            push_log(self.game, "You fall...")
        self.refresh()

    def action_or_move(self, dx: int, dy: int):
        if self.game.over: return
        try_move_player(self.game, dx, dy)
        self.end_turn()

    # ---- actions ----
    def on_rest(self):
        if self.game.over: return
        self.game.player.hp = min(self.game.player.max_hp, self.game.player.hp + 1)
        push_log(self.game, "You catch your breath.")
        self.end_turn()

    def on_potion(self):
        if self.game.over: return
        use_potion(self.game)
        self.end_turn()

    def on_new(self):
        self.game = new_floor(None)
        self.map_widget.setGame(self.game)
        self.refresh()
        self.map_widget.setFocus()

    def on_toggle(self):
        self.map_widget.toggleTiles()
        self.map_widget.setFocus()

    # ---- keyboard ----
    def keyPressEvent(self, e):
        key = e.key()
        mod = e.modifiers()

        # movement
        if key in (Qt.Key.Key_Up, Qt.Key.Key_W): return self.action_or_move(0, -1)
        if key in (Qt.Key.Key_Down, Qt.Key.Key_S): return self.action_or_move(0, 1)
        if key in (Qt.Key.Key_Left, Qt.Key.Key_A): return self.action_or_move(-1, 0)
        if key in (Qt.Key.Key_Right, Qt.Key.Key_D): return self.action_or_move(1, 0)

        # wait
        if key == Qt.Key.Key_Period and mod == Qt.KeyboardModifier.NoModifier:
            return self.action_or_move(0, 0)

        # rest / potion / new / toggle
        if key == Qt.Key.Key_R: return self.on_rest()
        if key == Qt.Key.Key_P: return self.on_potion()
        if key == Qt.Key.Key_N: return self.on_new()
        if key == Qt.Key.Key_T: return self.on_toggle()

        super().keyPressEvent(e)


# -------------------------
# ENTRY POINT
# -------------------------
def main():
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
