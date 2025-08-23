# ASCII Roguelike (Python, curses)

A simple ASCII dungeon crawler written in Python.  
The player is a Dwarf Slayer exploring procedurally generated dungeons, fighting goblins, trolls, and more.  
Features include line of sight, depth progression with stairs, potions, XP, and leveling.

---

## 📦 Requirements

- Python 3.8+  
- `curses` (built-in on Linux/macOS)  
- On **Windows**, install the shim:

    python -m pip install windows-curses

---

## ▶️ Run the game

Clone this repo and run:

    git clone https://github.com/AlexanderMetz/ascii-roguelike.git
    cd ascii-roguelike
    python roguelike.py

---

## 🎮 Controls

- **Arrows / WASD** → Move  
- **.** (dot) → Wait one turn  
- **R** → Rest (recover 1 HP, enemies move)  
- **P** → Drink potion  
- **Q** → Quit  
- **>** → Walk onto stairs to descend  

---

## ✨ Features

- Procedural dungeon generation (rooms + corridors)  
- Fog of war and line of sight  
- Player stats inspired by *Das Schwarze Auge* (DSA)  
- Enemies: Goblins, Orcs, Wolves, Archers, Trolls  
- Potions, stairs, XP and leveling system  
- Depth increases difficulty (trolls appear deeper down)  

---

## 📜 License

MIT — feel free to fork and extend!
