#!/usr/bin/env python3
"""
Peking Duck - a desktop pet mallard that waddles along the top of your taskbar.

Run it:   double-click peking_duck.pyw   (or:  pythonw peking_duck.pyw)
Needs:    Python 3.8+ for Windows (python.org installer includes everything)

Mouse:
  - Left-click            quack + hop (poke him 3x fast and he gets annoyed)
  - Double-click          open the "Ask Claude" chat window
  - Click and drag        pick him up; let go and he drops back to the taskbar
  - Hold cursor on him    petting -> hearts
  - Swipe cursor at him   he gets spooked and runs
  - Cursor near taskbar   sometimes he waddles over to say hi
  - Right-click           menu (Ask Claude, Disco!, Go for a flight, ... and Quit)

Random behaviours: walk, idle/blink, look around, peck, quack, flap, dance, nap,
plus two emotes: disco (stands tall, disco ball and all) and flight (loops around
the screen, then lands back on the taskbar).

Ask Claude: needs an Anthropic API key from https://console.anthropic.com
(the API is billed separately from a claude.ai subscription). The duck asks for
the key the first time and saves it in .peking_duck.json in your user folder,
or you can set the ANTHROPIC_API_KEY environment variable instead.

Helper modes (right-click > Health monitor / Detective / Cleanup crew), each with its own outfit:
  - Health monitor (doctor's head mirror): watches CPU/GPU temperatures. Sweats and fans
    himself when your PC runs hot, wears a scarf and shivers when it's chilly.
  - Detective (deerstalker + magnifying glass): checks Windows Defender, the firewall,
    Windows Update and app updates, runs quick virus scans, and writes a Case File.
  - Cleanup crew (hard hat + broom): empties the Recycle Bin, clears old temp files and
    tidies Downloads into folders (undoable). Always shows a preview and asks first.
Settings live under right-click > Settings.

Desktop icons (Windows): now and then he flies up to a visible desktop icon to
perch on it, peck it, or "borrow" it and carry it around before putting it back
exactly where it was. Right-click -> Desktop icons to trigger these or switch
them off. If the duck is ever closed mid-carry, the icon goes back the next time
he starts. (Borrowing is skipped when the desktop's "Auto arrange icons" is on.)
"""
import atexit
import collections
import ctypes
import json
import math
import os
import queue
import base64
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

if IS_WIN:  # makes pixels crisp and mouse coordinates match the real screen
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ------------------------------------------------------------------ settings
TICK_MS = 30          # frame time (~33 fps)
SCALE = None          # size of one art pixel in screen pixels; None = auto from DPI
WALK_SPEED = 0.45     # screen pixels per frame, multiplied by SCALE
KEY = "#ff00fe"       # "invisible" colour used for the transparent window background
OUTLINE = "#2b2620"

# Ask Claude
API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-5-5"   # fast + cheap; "claude-sonnet-5-5" for smarter answers
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".peking_duck.json")
SYSTEM_PROMPT = ("You are Claude, made by Anthropic, chatting with the user through "
                 "'Peking Duck', their desktop-pet mallard. Be helpful and concise. "
                 "Reply in plain text without Markdown, since your answer is shown in a "
                 "small plain-text chat window.")

QUACKS = ["Quack!", "Quack quack!", "QUACK.", "Quack?", "*quack*",
          "Got any bread?", "Peking Duck, at your service."]

# ------------------------------------------------------------------ pixel art
# 24 x 21 art grid, duck faces right. "." = transparent.
# The normal (horizontal) duck sits in the bottom 18 rows; the top Y0 rows are
# headroom for the tall disco pose.
PAL = {
    "G": "#1d6b3c", "g": "#3fa364", "K": "#111111", "W": "#f4f1ea",
    "Y": "#f2c230", "y": "#c98f12", "B": "#6e3b23", "b": "#d3ccc0",
    "d": "#7d7266", "U": "#2f55b5", "w": "#ffffff", "T": "#ece8e0",
    "O": "#f28b25", "R": "#e0465a", "Z": "#a9c1ff", "N": "#ffd84a",
    "P": "#ff5fd2", "C": "#4fe3ff", "L": "#dfe6ee", "l": "#8a96a3",
    # outfits
    "h": "#9a7546", "H": "#5e4527", "m": "#3d3d3d", "a": "#f5c400", "A": "#c99a00",
    "x": "#e0b04e", "X": "#a8762a", "M": "#e9edf2", "n": "#9aa3ad", "e": "#f7f7f7",
    "r": "#d0342c", "q": "#9e2420", "S": "#7ec8ff", "D": "#c9bda8",
}
GW, GH = 24, 22
Y0 = 3
TOP = 1      # one spare row on top so hats fit on the tall disco pose

HEADS = {
    "normal": [".GGG......",
               "GGGGG.....",
               "GgGGGG....",
               "GGGGKG....",
               "GGGGGGYYY.",
               "GGGGGYYYy.",
               ".GGGG.....",
               ".WWWW....."],
    "blink":  [".GGG......",
               "GGGGG.....",
               "GgGGGG....",
               "GGGKKG....",
               "GGGGGGYYY.",
               "GGGGGYYYy.",
               ".GGGG.....",
               ".WWWW....."],
    "quack":  [".GGG......",
               "GGGGG.....",
               "GgGGGG....",
               "GGGGKGYYY.",
               "GGGGGG....",
               "GGGGGYYYy.",
               ".GGGG.....",
               ".WWWW....."],
}
BODY = ["..K........BBBBB..",
        ".KT......bbBBBBBB.",
        ".TTbbbbbbbbBBBBBB.",
        "..TbddddUUdbBBBBB.",
        "..TbddddwwdbbBBBb.",
        "...bbbbbbbbbbbbbb.",
        "....bbbbbbbbbbbb..",
        ".....bbbbbbbbbb..."]
# Upright body for the disco pose
TALL_BODY = ["..BBBBB...",
             ".BBBBBBB..",
             ".BBBBBBBb.",
             "bBBBBBBbb.",
             "bbBBBBbbb.",
             "bbbbbbbbb.",
             "bbbbbbbbb.",
             "Kbbbbbbbb.",
             "KTbbbbbbb.",
             ".TTbbbbb.."]
# name: (rows, x, y).  Normal-pose wings are offset by Y0 + body_dy; disco wings are absolute.
WINGS = {
    "up":   ([".....dd",
              "...dddd",
              "..ddddd",
              ".ddUUdd",
              "dddwwd."], 4, 5),
    "down": (["ddUUddd",
              ".dwwdd.",
              "..ddd..",
              "...d..."], 5, 13),
    "disco_up":   (["dd......",
                    "ddd.....",
                    ".ddd....",
                    "..ddd...",
                    "...dUd..",
                    "....dwd.",
                    ".....ddd"], 2, 3),
    "disco_down": (["ddd....",
                    ".dwd...",
                    "..dUd..",
                    "...ddd.",
                    "....ddd"], 13, 12),
}
LEGS = {
    "stand":   ["........O...O.....", "........OO..OO...."],
    "walk1":   [".......O.....O....", ".......OO....OO..."],
    "walk2":   [".........O..O.....", ".........OO.OO...."],
    "dangle1": ["........O...O.....", "........O...O....."],
    "dangle2": [".......O.....O....", "......O.......O..."],
    "tall1":   ["...........O..O...", "...........OO.OO.."],
    "tall2":   ["...........O...O..", "..........OO....OO"],
}
SPARK = ["..X..", "..X..", "XXXXX", "..X..", "..X.."]
GLYPHS = {
    "heart": [".RR.RR.", "RRRRRRR", "RRRRRRR", ".RRRRR.", "..RRR..", "...R..."],
    "z":     ["ZZZZZ", "...Z.", "..Z..", ".Z...", "ZZZZZ"],
    "note":  ["..NN.", "..N.N", "..N..", "..N..", "NNN..", "NNN.."],
    "spark_p": [r.replace("X", "P") for r in SPARK],
    "spark_c": [r.replace("X", "C") for r in SPARK],
    "spark_y": [r.replace("X", "N") for r in SPARK],
    "ball":  ["..LLL..", ".LlLlL.", "LlLlLlL", "LLlLlLL", "LlLlLlL", ".LlLlL.", "..LLL.."],
}

# Outfits. Hats and head extras sit relative to the head (x, y offsets from the head's
# top-left); props are held in front of the body and only show in normal standing poses.
HATS = {
    "detective": (["...hHh...",
                   "..hHhHh..",
                   "hhHhHhHhh"], -1, -3),
    "hardhat":   (["..aaaa...",
                   ".aaaaaa..",
                   "AAAAAAAAA"], -1, -3),
    "doctor":    ([".MM.",
                   "MnnM",
                   ".MM."], 3, -1),
}
HEAD_EXTRAS = {
    "doctor_band": (["eeeee"], 0, 1),
    "scarf":       (["rqrqr", "r....", "q...."], 0, 7),
    "blush":       (["RR"], 2, 4),
}
PROPS = {   # (rows, x, y) in normal-pose coordinates (y is offset by Y0 + body_dy)
    "magnifier": ([".mmm.",
                   "mLLLm",
                   "mLLLm",
                   "mLLLm",
                   ".mmm.",
                   "H....",
                   "H...."], 18, 6),
    "broom":     (["H......",
                   ".H.....",
                   "..H....",
                   "...H...",
                   "....H..",
                   "....H..",
                   "....H..",
                   "..xXxXx",
                   ".xXxXxX",
                   "xXxXxXx"], 16, 8),
}
GLYPHS["drop"] = [".S.", "SSS", "SSS", ".S."]
GLYPHS["dust"] = [".D.", "DDD", ".D."]

# pose = (head, legs, wing, head_dx, head_dy, body_dy)
POSE = ("normal", "stand", None, 0, 0, 0)


def stamp(px, rows, ox=0, oy=0):
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                px[(x + ox, y + oy)] = PAL[ch]
    return px


def is_tall(pose):
    return bool(pose[1]) and pose[1].startswith("tall")


def compose(pose, look=None):
    """Build the duck's pixels for a pose. look = (hat, extras, prop, prop_dx, prop_dy)."""
    hat, extras, prop, pdx, pdy = look or (None, (), None, 0, 0)
    head, legs, wing, hx, hy, by = pose
    px = {}
    tall = is_tall(pose)
    if tall:
        stamp(px, LEGS[legs], 0, 19)
        stamp(px, TALL_BODY, 8, 9)
        if wing:
            rows, ox, oy = WINGS[wing]
            stamp(px, rows, ox, oy)
        ax, ay = 10 + hx, 2 + hy
    else:
        if legs:
            stamp(px, LEGS[legs], 0, 16 + Y0)
        stamp(px, BODY, 0, 8 + Y0 + by)
        if wing:
            rows, ox, oy = WINGS[wing]
            stamp(px, rows, ox, oy + Y0 + by)
        ax, ay = 11 + hx, Y0 + hy + by
    stamp(px, HEADS[head], ax, ay)
    for e in extras:
        rows, dx, dy = HEAD_EXTRAS[e]
        stamp(px, rows, ax + dx, ay + dy)
    if hat:
        rows, dx, dy = HATS[hat]
        stamp(px, rows, ax + dx, ay + dy)
    if prop and legs and not tall:
        rows, x, y = PROPS[prop]
        stamp(px, rows, x + pdx, y + Y0 + by + pdy)
    return {(x, y + TOP): c for (x, y), c in px.items()}


def outlined(px, w, h, mirror=False):
    """Return {(x, y): colour} on a (w+2) x (h+2) grid with a dark outline added."""
    filled = {}
    for (x, y), c in px.items():
        if 0 <= x < w and 0 <= y < h:
            if mirror:
                x = w - 1 - x
            filled[(x + 1, y + 1)] = c
    out = {}
    for (x, y) in filled:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n not in filled:
                out[n] = OUTLINE
    out.update(filled)
    return out


def build_image(px, w, h, scale, mirror=False):
    img = tk.PhotoImage(width=w + 2, height=h + 2)
    for p, c in outlined(px, w, h, mirror).items():
        img.put(c, to=p)
    return img.zoom(scale) if scale > 1 else img


# ------------------------------------------------------------------ OS helpers
def work_area(root):
    """Screen area not covered by the taskbar (left, top, right, bottom)."""
    if IS_WIN:
        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
        r = RECT()
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0):
            return r.left, r.top, r.right, r.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - (80 if IS_MAC else 48)


Mon = collections.namedtuple("Mon", "l t r b wl wt wr wb")   # full screen rect + work area


def monitors(root):
    """Every connected monitor, left to right (work area = screen minus its taskbar)."""
    if IS_WIN:
        try:
            from ctypes import wintypes as wt

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                            ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]
            u = ctypes.WinDLL("user32")
            PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
            u.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), PROC, wt.LPARAM]
            u.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]
            found = []

            def cb(hmon, hdc, rc, lp):
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if u.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                    a, w = mi.rcMonitor, mi.rcWork
                    found.append(Mon(a.left, a.top, a.right, a.bottom, w.left, w.top, w.right, w.bottom))
                return True
            u.EnumDisplayMonitors(None, None, PROC(cb), 0)
            if found:
                return sorted(found, key=lambda m: (m.l, m.t))
        except Exception:
            pass
    return [Mon(0, 0, root.winfo_screenwidth(), root.winfo_screenheight(), *work_area(root))]


def auto_scale():
    if IS_WIN:
        try:
            return max(3, round(4 * ctypes.windll.user32.GetDpiForSystem() / 96))
        except Exception:
            pass
    return 3 if IS_MAC else 4


def hide_from_alt_tab(root):
    if not IS_WIN:
        return
    try:
        root.update_idletasks()
        u32 = ctypes.windll.user32
        hwnd = u32.GetParent(root.winfo_id())
        style = u32.GetWindowLongW(hwnd, -20)
        u32.SetWindowLongW(hwnd, -20, (style | 0x80) & ~0x40000)  # TOOLWINDOW, not APPWINDOW
    except Exception:
        pass


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# ------------------------------------------------------------------ desktop icons
Icon = collections.namedtuple("Icon", "index px py left top w h ox oy")
# px/py: item position (ListView client coords)   left/top/w/h: icon box on screen
# ox/oy: offset from item position to the icon box


class DesktopIcons:
    """Finds and moves Windows desktop icons. The desktop is a ListView owned by
    Explorer, so positions are read through a small buffer in Explorer's memory."""
    LVM_GETITEMCOUNT, LVM_GETITEMRECT, LVM_GETITEMPOSITION = 0x1004, 0x100E, 0x1010
    LVM_SETITEMPOSITION32 = 0x1031

    def __init__(self):
        self.lv = self.proc = self.buf = None
        self.movable = True
        if not IS_WIN:
            return
        try:
            self._api()
            self._connect()
        except Exception:
            self.lv = None

    def _api(self):
        from ctypes import wintypes as wt
        self.wt = wt
        u = self.u = ctypes.WinDLL("user32")     # private copies, so argtypes don't leak
        k = self.k = ctypes.WinDLL("kernel32")
        H, sz = wt.HWND, ctypes.c_size_t
        u.FindWindowW.argtypes, u.FindWindowW.restype = [wt.LPCWSTR, wt.LPCWSTR], H
        u.FindWindowExW.argtypes, u.FindWindowExW.restype = [H, H, wt.LPCWSTR, wt.LPCWSTR], H
        u.SendMessageTimeoutW.argtypes = [H, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                          ctypes.POINTER(sz)]
        u.SendMessageTimeoutW.restype = wt.LPARAM
        u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wt.DWORD)]
        u.ClientToScreen.argtypes = [H, ctypes.POINTER(wt.POINT)]
        u.ScreenToClient.argtypes = [H, ctypes.POINTER(wt.POINT)]
        u.WindowFromPoint.argtypes, u.WindowFromPoint.restype = [wt.POINT], H
        u.IsWindow.argtypes = [H]
        u.GetWindowLongW.argtypes, u.GetWindowLongW.restype = [H, ctypes.c_int], ctypes.c_long
        k.OpenProcess.argtypes, k.OpenProcess.restype = [wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE
        k.VirtualAllocEx.argtypes = [wt.HANDLE, wt.LPVOID, sz, wt.DWORD, wt.DWORD]
        k.VirtualAllocEx.restype = wt.LPVOID
        k.VirtualFreeEx.argtypes = [wt.HANDLE, wt.LPVOID, sz, wt.DWORD]
        k.ReadProcessMemory.argtypes = [wt.HANDLE, wt.LPCVOID, wt.LPVOID, sz, ctypes.POINTER(sz)]
        k.WriteProcessMemory.argtypes = [wt.HANDLE, wt.LPVOID, wt.LPCVOID, sz, ctypes.POINTER(sz)]
        k.CloseHandle.argtypes = [wt.HANDLE]

    def _connect(self):
        u, k, wt = self.u, self.k, self.wt
        progman = u.FindWindowW("Progman", None)
        dv = u.FindWindowExW(progman, None, "SHELLDLL_DefView", None) if progman else None
        w = None
        while not dv:                                  # some setups park it under a WorkerW
            w = u.FindWindowExW(None, w, "WorkerW", None)
            if not w:
                break
            dv = u.FindWindowExW(w, None, "SHELLDLL_DefView", None)
        lv = u.FindWindowExW(dv, None, "SysListView32", None) if dv else None
        if not lv:
            return
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(lv, ctypes.byref(pid))
        proc = k.OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, False, pid.value)
        if not proc:
            return
        buf = k.VirtualAllocEx(proc, None, 4096, 0x3000, 0x04)
        if not buf:
            k.CloseHandle(proc)
            return
        self.lv, self.proc, self.buf = lv, proc, buf

    def close(self):
        if self.proc:
            try:
                if self.buf:
                    self.k.VirtualFreeEx(self.proc, self.buf, 0, 0x8000)
                self.k.CloseHandle(self.proc)
            except Exception:
                pass
        self.lv = self.proc = self.buf = None

    @property
    def ok(self):
        if not IS_WIN:
            return False
        if self.lv and self.u.IsWindow(self.lv):
            return True
        self.close()                                   # Explorer restarted? reconnect
        try:
            self._connect()
        except Exception:
            pass
        return bool(self.lv)

    def _send(self, msg, w=0, l=0):
        res = ctypes.c_size_t(0)
        if not self.u.SendMessageTimeoutW(self.lv, msg, w, l, 0x0002, 300, ctypes.byref(res)):
            raise OSError("desktop not responding")
        return res.value

    def _write(self, obj):
        self.k.WriteProcessMemory(self.proc, self.buf, ctypes.byref(obj), ctypes.sizeof(obj), None)

    def _read(self, obj):
        self.k.ReadProcessMemory(self.proc, self.buf, ctypes.byref(obj), ctypes.sizeof(obj), None)
        return obj

    def icons(self):
        if not self.ok:
            return []
        wt, out = self.wt, []
        try:
            self.movable = not (self.u.GetWindowLongW(self.lv, -16) & 0x0100)   # LVS_AUTOARRANGE
            for i in range(min(self._send(self.LVM_GETITEMCOUNT), 300)):
                self._write(wt.RECT(1, 0, 0, 0))                                 # LVIR_ICON
                if not self._send(self.LVM_GETITEMRECT, i, self.buf):
                    continue
                rc = self._read(wt.RECT())
                if not self._send(self.LVM_GETITEMPOSITION, i, self.buf):
                    continue
                p = self._read(wt.POINT())
                tl = wt.POINT(rc.left, rc.top)
                self.u.ClientToScreen(self.lv, ctypes.byref(tl))
                w, h = rc.right - rc.left, rc.bottom - rc.top
                if w > 0 and h > 0:
                    out.append(Icon(i, p.x, p.y, tl.x, tl.y, w, h, rc.left - p.x, rc.top - p.y))
        except Exception:
            return []
        return out

    def visible(self, ic):
        """True if the icon isn't covered by a window."""
        try:
            pt = self.wt.POINT(ic.left + ic.w // 2, ic.top + ic.h // 2)
            return self.u.WindowFromPoint(pt) == self.lv
        except Exception:
            return False

    def set_pos(self, index, x, y):
        self._write(self.wt.POINT(int(x), int(y)))
        self._send(self.LVM_SETITEMPOSITION32, index, self.buf)

    def move_screen(self, ic, sx, sy):
        """Move an icon so its picture's top-left lands at screen point (sx, sy)."""
        c = self.wt.POINT(int(sx), int(sy))
        self.u.ScreenToClient(self.lv, ctypes.byref(c))
        self.set_pos(ic.index, c.x - ic.ox, c.y - ic.oy)

    def restore(self, ic):
        self.set_pos(ic.index, ic.px, ic.py)


# ------------------------------------------------------------------ Ask Claude window
GREEN, BG, FG = "#1d6b3c", "#fbfaf7", "#1f1f1f"


class AskClaude:
    def __init__(self, duck):
        self.duck, self.root = duck, duck.root
        self.win = None
        self.history = []
        self.busy = False
        self.results = queue.Queue()
        self.think_mark = None

    # -- window
    def open(self):
        if self.win is not None:
            self.win.deiconify()
            self.win.lift()
            self.input.focus_force()
            return
        d = self.duck
        F = d.font[0]
        w, h = 400, 480
        win = self.win = tk.Toplevel(self.root)
        win.title("Ask Claude - Peking Duck")
        win.attributes("-topmost", True)
        cx = int(d.x + d.sx + d.spr_w / 2)
        x = min(max(cx - w // 2, d.wl + 8), d.wr - w - 8)
        y = max(d.wt + 8, int(d.y + d.sy) - h - 16)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.minsize(300, 280)
        win.configure(bg=BG)
        win.protocol("WM_DELETE_WINDOW", win.withdraw)

        head = tk.Frame(win, bg=GREEN)
        head.pack(side="top", fill="x")
        tk.Label(head, text="Ask Claude", bg=GREEN, fg="white",
                 font=(F, 11, "bold"), padx=12, pady=8).pack(side="left")
        tk.Button(head, text="New chat", command=self.new_chat, relief="flat", bd=0,
                  bg="#2f8a52", fg="white", activebackground="#3fa364",
                  activeforeground="white", padx=10, cursor="hand2").pack(side="right", padx=8, pady=6)

        bottom = tk.Frame(win, bg="#ece8e0", padx=8, pady=8)
        bottom.pack(side="bottom", fill="x")
        self.input = tk.Text(bottom, height=3, wrap="word", font=(F, 10), relief="flat",
                             padx=8, pady=6, highlightthickness=1,
                             highlightbackground="#cfc8bc", highlightcolor=GREEN)
        self.input.pack(side="left", fill="both", expand=True)
        self.send_btn = tk.Button(bottom, text="Send", command=self.send, bg=GREEN, fg="white",
                                  relief="flat", bd=0, padx=14, font=(F, 10, "bold"),
                                  activebackground="#2f8a52", activeforeground="white",
                                  cursor="hand2")
        self.send_btn.pack(side="right", fill="y", padx=(8, 0))
        self.input.bind("<Return>", self._on_enter)

        body = tk.Frame(win, bg=BG)
        body.pack(side="top", fill="both", expand=True)
        self.chat = tk.Text(body, wrap="word", bg=BG, fg=FG, font=(F, 10), relief="flat",
                            padx=12, pady=10, state="disabled", cursor="arrow")
        sb = tk.Scrollbar(body, command=self.chat.yview)
        self.chat.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_config("You", foreground=GREEN, font=(F, 10, "bold"))
        self.chat.tag_config("Claude", foreground="#c15f3c", font=(F, 10, "bold"))
        self.chat.tag_config("msg", spacing3=12)
        self.chat.tag_config("err", foreground="#b3261e", spacing3=12)
        self.chat.tag_config("hint", foreground="#7a7a7a", font=(F, 9, "italic"), spacing3=12)

        self.write("Quack! Ask me anything. Enter sends, Shift+Enter adds a new line.", "hint")
        self.input.focus_force()
        self.root.after(150, self.poll)

    def _on_enter(self, e):
        if e.state & 0x0001:          # Shift+Enter -> newline
            return None
        self.send()
        return "break"

    def write(self, text, tag="msg", name=None):
        c = self.chat
        c.config(state="normal")
        if name:
            c.insert("end", name + "\n", name)
        c.insert("end", text.strip() + "\n", tag)
        c.config(state="disabled")
        c.see("end")

    def new_chat(self):
        if self.busy:
            return
        self.history = []
        self.chat.config(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.config(state="disabled")
        self.write("Fresh pond. What's up?", "hint")

    # -- key / model
    def api_key(self, force=False):
        cfg = load_config()
        key = "" if force else (os.environ.get("ANTHROPIC_API_KEY") or cfg.get("api_key", ""))
        if key:
            return key
        from tkinter import simpledialog
        key = simpledialog.askstring(
            "Claude API key",
            "Paste your Anthropic API key (from console.anthropic.com).\n"
            "It's saved on this computer in .peking_duck.json in your user folder.",
            show="*", parent=self.win if self.win is not None else self.root)
        if key:
            cfg["api_key"] = key.strip()
            save_config(cfg)
        return (key or "").strip()

    def model(self):
        return load_config().get("model", DEFAULT_MODEL)

    # -- talking to Claude
    def send(self):
        text = self.input.get("1.0", "end").strip()
        if not text or self.busy:
            return
        key = self.api_key()
        if not key:
            self.write("No API key yet, so I can't ask Claude.", "err")
            return
        self.input.delete("1.0", "end")
        self.write(text, "msg", "You")
        self.history.append({"role": "user", "content": text})
        self.busy = True
        self.send_btn.config(state="disabled")
        self.think_mark = self.chat.index("end-1c")
        self.write("Claude is thinking...", "hint")
        self.duck.react("think", "Hmm...")
        msgs = list(self.history[-41:])          # keep it short; always starts with a user turn
        threading.Thread(target=self.worker, args=(msgs, key, self.model()), daemon=True).start()

    def worker(self, msgs, key, model):
        body = json.dumps({"model": model, "max_tokens": 1024,
                           "system": SYSTEM_PROMPT, "messages": msgs}).encode("utf-8")
        req = urllib.request.Request(API_URL, data=body, method="POST", headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            text = "".join(b.get("text", "") for b in data.get("content", [])
                           if b.get("type") == "text").strip()
            self.results.put(("ok", text or "(Claude sent back an empty reply.)"))
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:
                msg = e.reason
            if e.code == 401:
                msg = "That API key wasn't accepted. Right-click the duck and choose 'Change API key...'."
            self.results.put(("err", f"Error {e.code}: {msg}"))
        except Exception as e:
            self.results.put(("err", f"Couldn't reach Claude: {e}"))

    def poll(self):
        try:
            while True:
                self.finish(*self.results.get_nowait())
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.root.after(150, self.poll)

    def finish(self, kind, text):
        c = self.chat
        c.config(state="normal")
        if self.think_mark:
            c.delete(self.think_mark, "end-1c")
        c.config(state="disabled")
        self.busy = False
        self.send_btn.config(state="normal")
        if kind == "ok":
            self.history.append({"role": "assistant", "content": text})
            self.write(text, "msg", "Claude")
            self.duck.react("quack", random.choice(["Got it!", "Quack! Answered.", "Ta-da!"]))
        else:
            self.history.pop()                    # drop the unanswered question
            self.write(text, "err")
            self.duck.react("quack", "Uh oh...")
        self.win.deiconify()


# ------------------------------------------------------------------ helper modes: shared bits
NO_WINDOW = 0x08000000 if IS_WIN else 0          # don't flash console windows
DEFAULTS = {
    "health_warm": 75, "health_hot": 85, "health_cool": 40, "health_poll": 5,
    "health_announce": 10, "lhm_port": 8085,
    "det_auto_hours": 6, "det_app_updates": True,
    "temp_age_days": 2,
}


def run_cmd(args, timeout=60):
    r = subprocess.run(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                       creationflags=NO_WINDOW)

    def dec(b):
        return (b or b"").decode("utf-8", "replace")
    return r.returncode, dec(r.stdout), dec(r.stderr)


def run_ps(script, timeout=60):
    """Run a PowerShell script hidden; returns (exit code, stdout, stderr)."""
    full = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
            "$ProgressPreference='SilentlyContinue'\n" + script)
    enc = base64.b64encode(full.encode("utf-16-le")).decode("ascii")
    return run_cmd(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-EncodedCommand", enc], timeout)


def ps_json(script, timeout=60):
    rc, out, err = run_ps(script, timeout)
    out = out.strip().lstrip("\ufeff")
    if not out:
        raise RuntimeError((err or "no output").strip()[:200])
    return json.loads(out)


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def open_uri(uri):
    try:
        if IS_WIN:
            os.startfile(uri)
        elif IS_MAC:
            subprocess.Popen(["open", uri])
        else:
            subprocess.Popen(["xdg-open", uri])
    except Exception:
        pass


# ------------------------------------------------------------------ health monitor: sensors
def sensor_kind(identifier):
    """'/amdcpu/0/temperature/2' -> 'cpu', '/gpu-nvidia/0/temperature/0' -> 'gpu'."""
    first = str(identifier).lower().strip("/").split("/")[0]
    return "cpu" if "cpu" in first else "gpu" if "gpu" in first else None


def pick_temp(cands, prefer):
    cands = [(n, v) for n, v in cands if 0 < v < 130]
    if not cands:
        return None
    for p in prefer:
        for n, v in cands:
            if p in n.lower():
                return v
    return max(v for _, v in cands)


CPU_PREFER = ("package", "tctl", "tdie")
GPU_PREFER = ("gpu core", "core")


def parse_lhm_json(root):
    """Pull CPU/GPU temperatures out of LibreHardwareMonitor's /data.json tree."""
    found = {"cpu": [], "gpu": []}

    def walk(node, hint):
        img = str(node.get("ImageURL", "")).lower()
        if "cpu" in img:
            hint = "cpu"
        elif any(k in img for k in ("nvidia", "ati.", "gpu")):
            hint = "gpu"
        kids = node.get("Children") or []
        m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*\u00b0\s*C", str(node.get("Value", "")))
        if m and not kids:
            kind = sensor_kind(node.get("SensorId", "")) or hint
            if kind:
                found[kind].append((str(node.get("Text", "")), float(m.group(1).replace(",", "."))))
        for k in kids:
            walk(k, hint)
    walk(root, None)
    out = {"cpu": pick_temp(found["cpu"], CPU_PREFER), "gpu": pick_temp(found["gpu"], GPU_PREFER)}
    return out if out["cpu"] is not None or out["gpu"] is not None else None


LHM_WMI_PS = (
    "$s = Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor "
    "-Filter \"SensorType='Temperature'\" -ErrorAction Stop | Select-Object Name,Value,Identifier\n"
    "ConvertTo-Json -InputObject @($s) -Compress")


class Sensors:
    """CPU/GPU temperatures. Tries LibreHardwareMonitor's web server, then its WMI feed,
    then nvidia-smi (NVIDIA cards only)."""

    def __init__(self, port_fn):
        self.port_fn = port_fn
        self.wmi_retry = 0.0
        self.wmi_cache = (0.0, None)
        sys_smi = r"C:\Windows\System32\nvidia-smi.exe"
        self.nvsmi = shutil.which("nvidia-smi") or (sys_smi if IS_WIN and os.path.exists(sys_smi) else None)
        self.prev_times = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def read(self):
        out = {"cpu": None, "gpu": None, "gpu_load": None, "cpu_load": None, "source": "none"}
        srcs = []
        temps = self.lhm_http()
        if temps is None and IS_WIN:
            temps = self.lhm_wmi()
        if temps:
            out["cpu"], out["gpu"] = temps.get("cpu"), temps.get("gpu")
            srcs.append("LibreHardwareMonitor")
        if out["gpu"] is None and self.nvsmi:
            g = self.nvidia()
            if g:
                out["gpu"], out["gpu_load"] = g
                srcs.append("nvidia-smi")
        out["cpu_load"] = self.cpu_load()
        out["source"] = " + ".join(srcs) or "none"
        return out

    def lhm_http(self):
        try:
            url = f"http://127.0.0.1:{int(self.port_fn())}/data.json"
            with self.opener.open(url, timeout=1.5) as r:
                return parse_lhm_json(json.loads(r.read().decode("utf-8", "replace")))
        except Exception:
            return None

    def lhm_wmi(self):
        now = time.time()
        if now - self.wmi_cache[0] < 15:            # PowerShell is heavy: reuse for 15 s
            return self.wmi_cache[1]
        if now < self.wmi_retry:
            return None
        try:
            data = ps_json(LHM_WMI_PS, 20)
            data = [data] if isinstance(data, dict) else data
            found = {"cpu": [], "gpu": []}
            for s in data or []:
                kind = sensor_kind(s.get("Identifier", ""))
                if kind and s.get("Value") is not None:
                    found[kind].append((str(s.get("Name", "")), float(s["Value"])))
            temps = {"cpu": pick_temp(found["cpu"], CPU_PREFER), "gpu": pick_temp(found["gpu"], GPU_PREFER)}
            if temps["cpu"] is None and temps["gpu"] is None:
                raise RuntimeError("no sensors")
            self.wmi_cache = (now, temps)
            return temps
        except Exception:
            self.wmi_retry = now + 120                  # not running; check again in 2 min
            return None

    def nvidia(self):
        try:
            rc, out, _ = run_cmd([self.nvsmi, "--query-gpu=temperature.gpu,utilization.gpu",
                                  "--format=csv,noheader,nounits"], 5)
            parts = [p.strip() for p in out.strip().splitlines()[0].split(",")]
            temp = float(parts[0])
            try:
                load = float(parts[1])
            except (IndexError, ValueError):
                load = None
            return temp, load
        except Exception:
            return None

    def cpu_load(self):
        if not IS_WIN:
            return None
        try:
            from ctypes import wintypes as wt
            idle, kern, user = wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
            cur = tuple((f.dwHighDateTime << 32) | f.dwLowDateTime for f in (idle, kern, user))
            prev, self.prev_times = self.prev_times, cur
            if not prev:
                return None
            di, dk, du = (c - p for c, p in zip(cur, prev))
            total = dk + du                             # kernel time includes idle time
            return max(0.0, min(100.0, 100.0 * (total - di) / total)) if total else None
        except Exception:
            return None


# ------------------------------------------------------------------ detective: security + updates
MPCMD = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Windows Defender", "MpCmdRun.exe")

STATUS_PS = r"""
$o = [ordered]@{}
try {
  $m = Get-MpComputerStatus -ErrorAction Stop
  $o.av = $m.AntivirusEnabled; $o.rtp = $m.RealTimeProtectionEnabled
  $o.sigAge = $m.AntivirusSignatureAge; $o.quickAge = $m.QuickScanAge
  $o.mode = "$($m.AMRunningMode)"
} catch { $o.mpError = $_.Exception.Message }
try { $o.avProducts = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop | ForEach-Object { $_.displayName }) } catch {}
try { $o.firewall = @(Get-NetFirewallProfile -ErrorAction Stop | ForEach-Object { "$($_.Name)=$($_.Enabled)" }) } catch {}
$o.rebootPending = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') -or (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')
ConvertTo-Json -InputObject $o -Compress
"""

WU_PS = r"""
$s = New-Object -ComObject Microsoft.Update.Session
$r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and IsHidden=0")
ConvertTo-Json -InputObject @($r.Updates | ForEach-Object { $_.Title }) -Compress
"""


def security_status():
    return ps_json(STATUS_PS, 90)


def windows_updates():
    r = ps_json(WU_PS, 600)
    return [r] if isinstance(r, str) else list(r or [])


def parse_winget(text):
    """Rows of (name, id, current, available) from `winget upgrade`; None if no table."""
    lines = [ln.split("\r")[-1].rstrip() for ln in text.splitlines()]
    for i, ln in enumerate(lines):
        if i and re.match(r"^-{10,}$", ln.strip()):
            header = lines[i - 1]
            break
    else:
        return None
    cols = {m.group(0).lower(): m.start() for m in re.finditer(r"\S+", header)}
    if not all(k in cols for k in ("name", "id", "version", "available")):
        return None
    order = sorted(cols.values())

    def cell(line, key):
        start = cols[key]
        nxt = [c for c in order if c > start]
        return line[start:nxt[0] if nxt else None].strip()
    rows = []
    for ln in lines[i + 1:]:
        if not ln.strip() or re.match(r"^\d+\s+\S+", ln.strip()) and "upgrade" in ln.lower():
            break
        rows.append((cell(ln, "name"), cell(ln, "id"), cell(ln, "version"), cell(ln, "available")))
    return rows


def app_updates():
    exe = shutil.which("winget")
    if not exe:
        return None
    base = [exe, "upgrade", "--accept-source-agreements"]
    for args in (base + ["--disable-interactivity"], base):
        rc, out, _ = run_cmd(args, 300)
        rows = parse_winget(out)
        if rows is not None:
            return rows
        low = out.lower()
        if "no applicable upgrade" in low or "no installed package" in low:
            return []
    return None


def investigate_job(include_apps):
    rep = {}
    try:
        rep["status"] = security_status()
    except Exception as e:
        rep["status"] = {"mpError": str(e)}
    try:
        rep["win_updates"] = windows_updates()
    except Exception as e:
        rep["win_updates_error"] = str(e)
    if include_apps:
        try:
            rep["apps"] = app_updates()
        except Exception:
            rep["apps"] = None
    return rep


def case_items(rep):
    """(ok, text) findings for the case file. ok: True = fine, False = clue, None = unknown."""
    items = []
    st = rep.get("status") or {}
    avs = st.get("avProducts") or []
    passive = str(st.get("mode", "")).lower().startswith("passive")
    if st.get("av") is None and not avs:
        items.append((None, "Couldn't read your antivirus status."))
    elif passive or st.get("av") is False:
        items.append((True if avs else False,
                      f"Antivirus: {', '.join(avs) or 'none found!'} (Windows Defender isn't the active one)"))
    else:
        items.append((bool(st.get("rtp")),
                      "Windows Defender real-time protection is " + ("on" if st.get("rtp") else "OFF")))
        age = st.get("sigAge")
        if age is not None:
            items.append((age <= 3, f"Virus definitions are {age} day{'s' if age != 1 else ''} old"))
        q = st.get("quickAge")
        if q is not None:
            items.append((q <= 14, "No quick scan on record" if q > 10000
                          else f"Last quick scan: {q} day{'s' if q != 1 else ''} ago"))
    fw = st.get("firewall") or []
    if fw:
        off = [f.split("=")[0] for f in fw if f.lower().endswith("=false")]
        items.append((not off, "Firewall is on for every network type" if not off
                      else "Firewall is OFF for: " + ", ".join(off)))
    if "win_updates" in rep:
        n = len(rep["win_updates"])
        items.append((n == 0, "Windows is up to date" if n == 0 else f"{n} Windows update{'s' if n != 1 else ''} waiting"))
    elif rep.get("win_updates_error"):
        items.append((None, "Couldn't check Windows Update"))
    if st.get("rebootPending"):
        items.append((False, "A restart is pending to finish installing updates"))
    if "apps" in rep:
        apps = rep["apps"]
        if apps is None:
            items.append((None, "Couldn't check app updates (winget not available)"))
        else:
            items.append((not apps, "All your apps are up to date" if not apps
                          else f"{len(apps)} app update{'s' if len(apps) != 1 else ''} available"))
    return items


def scan_job():
    if not os.path.exists(MPCMD):
        raise RuntimeError("Windows Defender's scanner wasn't found")
    return run_cmd([MPCMD, "-Scan", "-ScanType", "1"], 3 * 3600)[0]


def defs_job():
    if not os.path.exists(MPCMD):
        raise RuntimeError("Windows Defender's updater wasn't found")
    return run_cmd([MPCMD, "-SignatureUpdate"], 900)[0]


# ------------------------------------------------------------------ cleanup crew
DOWNLOAD_FOLDERS = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".svg", ".tif", ".tiff", ".ico"},
    "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".txt", ".rtf",
                  ".odt", ".ods", ".md"},
    "Installers": {".exe", ".msi", ".msix", ".appx", ".appxbundle", ".msixbundle"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Videos": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".m4v"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma"},
}
SKIP_EXT = {".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload", ".ini", ".lnk"}


def is_link_dir(p):
    """Symlinks and junctions: never walk into them (they can point anywhere)."""
    try:
        st = os.lstat(p)
        return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)
    except OSError:
        return True


def safe_walk(top):
    for d, dirs, names in os.walk(top):
        dirs[:] = [x for x in dirs if not is_link_dir(os.path.join(d, x))]
        yield d, dirs, names


def downloads_dir():
    if IS_WIN:
        try:
            class GUID(ctypes.Structure):
                _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16),
                            ("d", ctypes.c_ubyte * 8)]
            g = GUID(0x374DE290, 0x123F, 0x4565,
                     (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
            p = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
                path = p.value
                ctypes.windll.ole32.CoTaskMemFree(p)
                return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


def recycle_bin_info():
    if not IS_WIN:
        return None
    try:
        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint32), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
            return info.i64Size, info.i64NumItems
    except Exception:
        pass
    return None


def empty_recycle_bin():
    try:   # no confirmation/progress/sound flags: we already asked in our own window
        return ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7) == 0
    except Exception:
        return False


def fixed_drives():
    out = []
    if IS_WIN:
        try:
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if mask & (1 << i):
                    root = f"{chr(65 + i)}:\\"
                    if ctypes.windll.kernel32.GetDriveTypeW(root) == 3:      # fixed disk
                        u = shutil.disk_usage(root)
                        out.append((root[:2], u.free, u.total))
        except Exception:
            pass
    else:
        u = shutil.disk_usage("/")
        out.append(("/", u.free, u.total))
    return out


def cleanup_scan(age_days, temp_dir=None, dl_dir=None):
    """Measure what could be cleaned. Nothing is changed here."""
    temp = temp_dir or tempfile.gettempdir()
    cutoff = time.time() - float(age_days) * 86400
    files, size = [], 0
    for d, dirs, names in safe_walk(temp):
        for n in names:
            p = os.path.join(d, n)
            try:
                st = os.lstat(p)
                if stat.S_ISREG(st.st_mode) and st.st_mtime < cutoff:
                    files.append(p)
                    size += st.st_size
            except OSError:
                pass
    dl = dl_dir or downloads_dir()
    plan = []
    try:
        names = os.listdir(dl)
    except OSError:
        names = []
    recent = time.time() - 600          # leave anything touched in the last 10 minutes
    for n in names:
        p = os.path.join(dl, n)
        ext = os.path.splitext(n)[1].lower()
        if ext in SKIP_EXT or n.startswith(("~$", ".")):
            continue
        try:
            if not os.path.isfile(p) or os.path.islink(p) or os.path.getmtime(p) > recent:
                continue
        except OSError:
            continue
        folder = next((f for f, exts in DOWNLOAD_FOLDERS.items() if ext in exts), None)
        if folder:
            plan.append((p, os.path.join(dl, folder, n)))
    return {"recycle": recycle_bin_info(), "temp": (temp, files, size, cutoff),
            "downloads": (dl, plan), "drives": fixed_drives()}


def unique_path(p):
    if not os.path.exists(p):
        return p
    base, ext = os.path.splitext(p)
    i = 2
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def cleanup_run(scan, do_recycle, do_temp, do_downloads):
    freed, skipped, moved = 0, 0, []
    rb = scan.get("recycle")
    if do_recycle and rb and rb[1] > 0 and empty_recycle_bin():
        freed += rb[0]
    if do_temp:
        temp, files, _, cutoff = scan["temp"]
        for p in files:
            try:
                sz = os.lstat(p).st_size
                os.remove(p)
                freed += sz
            except OSError:
                skipped += 1                          # in use by a running program
        dirs = [d for d, _, _ in safe_walk(temp) if os.path.normcase(d) != os.path.normcase(temp)]
        for d in sorted(dirs, key=len, reverse=True):  # deepest first; only old, empty folders
            try:
                if os.path.getmtime(d) < cutoff and not os.listdir(d):
                    os.rmdir(d)
            except OSError:
                pass
    if do_downloads:
        for src, dst in scan["downloads"][1]:
            try:
                if not os.path.exists(src):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                dst = unique_path(dst)
                shutil.move(src, dst)
                moved.append([dst, src])
            except OSError:
                skipped += 1
    return {"freed": freed, "skipped": skipped, "moved": moved}


def undo_tidy(log):
    back = 0
    for dst, src in reversed(log):
        try:
            if os.path.exists(dst) and not os.path.exists(src):
                shutil.move(dst, src)
                back += 1
        except OSError:
            pass
    for d in {os.path.dirname(dst) for dst, _ in log}:
        try:
            os.rmdir(d)                               # only succeeds if now empty
        except OSError:
            pass
    return back


# ------------------------------------------------------------------ helper windows
def styled_button(parent, text, cmd, bg=GREEN, fg="white", active="#2f8a52"):
    return tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, bg=bg, fg=fg,
                     activebackground=active, activeforeground=fg, padx=10, pady=4, cursor="hand2")


def place_near_duck(win, duck, w, h):
    cx = int(duck.x + duck.sx + duck.spr_w / 2)
    x = min(max(cx - w // 2, duck.wl + 8), duck.wr - w - 8)
    y = max(duck.wt + 8, int(duck.y + duck.sy) - h - 16)
    win.geometry(f"{w}x{h}+{x}+{y}")


class CaseFile:
    """Detective Duck's report window."""
    BROWN = "#5e4527"

    def __init__(self, duck):
        self.duck, self.win = duck, None

    def show(self, rep):
        d = self.duck
        F = d.font[0]
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        win = self.win = tk.Toplevel(d.root)
        win.title("Case File - Detective Duck")
        win.attributes("-topmost", True)
        win.configure(bg=BG)
        place_near_duck(win, d, 470, 540)
        head = tk.Frame(win, bg=self.BROWN)
        head.pack(side="top", fill="x")
        tk.Label(head, text="CASE FILE", bg=self.BROWN, fg="white", font=(F, 12, "bold"),
                 padx=12, pady=8).pack(side="left")
        tk.Label(head, text=time.strftime("%b %d, %I:%M %p"), bg=self.BROWN, fg="#e8dcc8",
                 font=(F, 9), padx=12).pack(side="right")

        btns = tk.Frame(win, bg="#ece8e0", padx=10, pady=8)
        btns.pack(side="bottom", fill="x")
        row1, row2 = tk.Frame(btns, bg="#ece8e0"), tk.Frame(btns, bg="#ece8e0")
        row1.pack(fill="x")
        row2.pack(fill="x", pady=(6, 0))
        for text, cmd in (("Quick virus scan", d.quick_scan), ("Update definitions", d.update_definitions),
                          ("Investigate again", d.investigate)):
            styled_button(row1, text, cmd, bg=self.BROWN, active="#7a5b36").pack(side="left", padx=(0, 6))
        styled_button(row2, "Windows Update", lambda: open_uri("ms-settings:windowsupdate")).pack(side="left", padx=(0, 6))
        styled_button(row2, "Windows Security", lambda: open_uri("windowsdefender:")).pack(side="left", padx=(0, 6))
        apps = rep.get("apps") or []
        if apps:
            styled_button(row2, f"Update {len(apps)} app{'s' if len(apps) != 1 else ''}",
                          d.update_apps).pack(side="left")

        txt = tk.Text(win, wrap="word", bg=BG, fg=FG, font=(F, 10), relief="flat", padx=14, pady=12)
        txt.pack(side="top", fill="both", expand=True)
        txt.tag_config("ok", foreground="#2e7d32")
        txt.tag_config("warn", foreground="#c25e00", font=(F, 10, "bold"))
        txt.tag_config("unk", foreground="#777777")
        txt.tag_config("h", font=(F, 10, "bold"), spacing1=10)
        txt.tag_config("small", foreground="#555555", font=(F, 9))
        for ok, line in case_items(rep):
            sym, tag = ("✔", "ok") if ok else (("⚠", "warn") if ok is False else ("?", "unk"))
            txt.insert("end", f"{sym}  {line}\n", tag)
        ups = rep.get("win_updates") or []
        if ups:
            txt.insert("end", "\nWindows updates waiting\n", "h")
            for t in ups[:12]:
                txt.insert("end", f"  • {t}\n", "small")
        if apps:
            txt.insert("end", "\nApp updates available\n", "h")
            for name, _id, cur, new in apps[:30]:
                txt.insert("end", f"  • {name}: {cur} → {new}\n", "small")
        txt.insert("end", "\nDetective Duck only looks. Nothing gets installed or changed "
                          "unless you press a button.", "unk")
        txt.config(state="disabled")


class CleanupWindow:
    YELLOW = "#f5c400"

    def __init__(self, duck):
        self.duck, self.win, self.scan = duck, None, None

    def open(self):
        if self.win is not None:
            try:
                self.win.deiconify()
                self.win.lift()
                self.rescan()
                return
            except tk.TclError:
                self.win = None
        d = self.duck
        F = d.font[0]
        win = self.win = tk.Toplevel(d.root)
        win.title("Cleanup Crew")
        win.attributes("-topmost", True)
        win.configure(bg=BG)
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        place_near_duck(win, d, 470, 440)
        head = tk.Frame(win, bg=self.YELLOW)
        head.pack(fill="x")
        tk.Label(head, text="CLEANUP CREW", bg=self.YELLOW, fg="#2b2620", font=(F, 12, "bold"),
                 padx=12, pady=8).pack(side="left")

        body = tk.Frame(win, bg=BG, padx=14, pady=10)
        body.pack(fill="both", expand=True)
        self.drives = tk.Label(body, text="", bg=BG, fg=FG, font=(F, 9), justify="left", anchor="w")
        self.drives.pack(fill="x", pady=(0, 8))
        self.v_rb, self.v_tmp, self.v_dl = (tk.BooleanVar(win, value=True) for _ in range(3))
        self.c_rb = tk.Checkbutton(body, variable=self.v_rb, bg=BG, anchor="w", justify="left", font=(F, 10))
        self.c_tmp = tk.Checkbutton(body, variable=self.v_tmp, bg=BG, anchor="w", justify="left", font=(F, 10))
        self.c_dl = tk.Checkbutton(body, variable=self.v_dl, bg=BG, anchor="w", justify="left", font=(F, 10))
        for c in (self.c_rb, self.c_tmp, self.c_dl):
            c.pack(fill="x", pady=3)
        self.status = tk.Label(body, text="", bg=BG, fg="#555555", font=(F, 9, "italic"),
                               justify="left", anchor="w", wraplength=430)
        self.status.pack(fill="x", pady=(10, 0))

        btns = tk.Frame(win, bg="#ece8e0", padx=10, pady=8)
        btns.pack(side="bottom", fill="x")
        self.go_btn = styled_button(btns, "Clean up!", self.go, bg="#c99a00", active="#a88000")
        self.go_btn.pack(side="left", padx=(0, 6))
        self.undo_btn = styled_button(btns, "Undo Downloads tidy", self.duck.undo_tidy)
        self.undo_btn.pack(side="left", padx=(0, 6))
        styled_button(btns, "Rescan", self.rescan).pack(side="left", padx=(0, 6))
        if IS_WIN:
            styled_button(btns, "Windows Disk Cleanup", self.disk_cleanup).pack(side="left")
        self.rescan()

    def disk_cleanup(self):
        try:
            subprocess.Popen(["cleanmgr"])
        except Exception:
            pass

    def rescan(self):
        if self.win is None:
            return
        self.status.config(text="Measuring...")
        self.go_btn.config(state="disabled")
        self.undo_btn.config(state="normal" if load_config().get("downloads_undo") else "disabled")
        age = self.duck.opt("temp_age_days")
        self.duck.run_bg(lambda: cleanup_scan(age), self.on_scan)

    def on_scan(self, res):
        if self.win is None:
            return
        if isinstance(res, Exception):
            self.status.config(text=f"Couldn't measure: {res}")
            return
        self.scan = res
        lines = []
        for label, free, total in res["drives"]:
            pct = free / total * 100 if total else 0
            warn = "   ⚠ almost full!" if pct < 10 else ""
            lines.append(f"{label}  {human_size(free)} free of {human_size(total)} ({pct:.0f}% free){warn}")
        self.drives.config(text="\n".join(lines) or "")
        rb = res["recycle"]
        if rb is None:
            self.c_rb.config(text="Empty the Recycle Bin (size unknown)")
        else:
            self.c_rb.config(text=f"Empty the Recycle Bin  ({human_size(rb[0])}, {rb[1]:,} item{'s' if rb[1] != 1 else ''})")
            if rb[1] == 0:
                self.v_rb.set(False)
        _, files, size, _ = res["temp"]
        age = self.duck.opt("temp_age_days")
        self.c_tmp.config(text=f"Delete temp files older than {age} day{'s' if float(age) != 1 else ''}  "
                               f"({human_size(size)}, {len(files):,} files)")
        if not files:
            self.v_tmp.set(False)
        plan = res["downloads"][1]
        counts = collections.Counter(os.path.basename(os.path.dirname(dst)) for _, dst in plan)
        detail = ", ".join(f"{k} {v}" for k, v in counts.most_common()) or "nothing to sort"
        self.c_dl.config(text=f"Tidy Downloads into folders  ({len(plan)} files: {detail})")
        if not plan:
            self.v_dl.set(False)
        self.status.config(text="Pick what to clean, then press Clean up! "
                                "Deleted items don't go to the Recycle Bin. Downloads tidying can be undone.")
        self.go_btn.config(state="normal")

    def go(self):
        from tkinter import messagebox
        if not self.scan:
            return
        picks = (self.v_rb.get(), self.v_tmp.get(), self.v_dl.get())
        if not any(picks):
            self.status.config(text="Nothing selected.")
            return
        what = [t for t, on in zip(("empty the Recycle Bin", "permanently delete old temp files",
                                    "move Downloads files into folders"), picks) if on]
        if not messagebox.askyesno("Cleanup Crew", "The duck will " + ", ".join(what) + ".\n\nGo ahead?",
                                   parent=self.win):
            return
        self.go_btn.config(state="disabled")
        self.status.config(text="Sweeping...")
        self.duck.start_clean(self.scan, picks, self.on_done)

    def on_done(self, res):
        if self.win is None:
            return
        if isinstance(res, Exception):
            self.status.config(text=f"Something went wrong: {res}")
        else:
            msg = f"Done! Freed {human_size(res['freed'])}"
            if res["moved"]:
                msg += f" and sorted {len(res['moved'])} download{'s' if len(res['moved']) != 1 else ''}"
            if res["skipped"]:
                msg += f". Skipped {res['skipped']} item{'s' if res['skipped'] != 1 else ''} that were in use"
            self.status.config(text=msg + ".")
        self.duck.root.after(1500, self.rescan)


class SettingsWindow:
    TABS = {
        "Health": [("health_warm", "Warm at (°C)"), ("health_hot", "Hot at (°C)"),
                   ("health_cool", "Chilly below (°C)"), ("health_poll", "Check every (seconds)"),
                   ("health_announce", "Say temps every (minutes, 0 = never)"),
                   ("lhm_port", "LibreHardwareMonitor web server port")],
        "Detective": [("det_auto_hours", "Auto-investigate every (hours, 0 = off)")],
        "Cleanup": [("temp_age_days", "Only delete temp files older than (days)")],
    }
    HEALTH_HELP = (
        "Where temperatures come from:\n"
        "• NVIDIA graphics cards work right away (no setup).\n"
        "• For CPU (and AMD/Intel graphics) temps, install the free LibreHardwareMonitor:\n"
        "   1. Download it from github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases\n"
        "   2. Run it as administrator (it needs that to read sensors)\n"
        "   3. In its menu: Options > Remote Web Server > Run\n"
        "   4. Optional: Options > Start Minimized and Run On Windows Startup\n"
        "If Windows Firewall asks about LibreHardwareMonitor, you can click Cancel. "
        "The duck reads it from this PC only.")

    def __init__(self, duck):
        self.duck, self.win = duck, None

    def open(self):
        from tkinter import ttk
        d = self.duck
        if self.win is not None:
            try:
                self.win.deiconify()
                self.win.lift()
                return
            except tk.TclError:
                self.win = None
        F = d.font[0]
        win = self.win = tk.Toplevel(d.root)
        win.title("Peking Duck - Settings")
        win.attributes("-topmost", True)
        win.configure(bg=BG)
        win.protocol("WM_DELETE_WINDOW", self.close)
        place_near_duck(win, d, 520, 520)
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.vars = {}
        frames = {}
        for tab in ("Health", "Detective", "Cleanup", "General"):
            f = tk.Frame(nb, bg=BG, padx=14, pady=12)
            nb.add(f, text=tab)
            frames[tab] = f
            for r, (key, label) in enumerate(self.TABS.get(tab, [])):
                tk.Label(f, text=label, bg=BG, font=(F, 10), anchor="w").grid(row=r, column=0, sticky="w", pady=3)
                v = self.vars[key] = tk.StringVar(win, value=str(d.opt(key)))
                tk.Entry(f, textvariable=v, width=8, font=(F, 10)).grid(row=r, column=1, sticky="w", padx=8)

        hf = frames["Health"]
        tk.Label(hf, text=self.HEALTH_HELP, bg=BG, fg="#444444", font=(F, 9), justify="left",
                 wraplength=460).grid(row=10, column=0, columnspan=2, sticky="w", pady=(14, 6))
        self.test_lbl = tk.Label(hf, text="", bg=BG, fg=GREEN, font=(F, 9, "bold"), justify="left", wraplength=460)
        styled_button(hf, "Test readings", self.test).grid(row=11, column=0, sticky="w")
        self.test_lbl.grid(row=12, column=0, columnspan=2, sticky="w", pady=6)

        df = frames["Detective"]
        self.v_apps = tk.BooleanVar(win, value=bool(d.opt("det_app_updates")))
        tk.Checkbutton(df, text="Also check for app updates (uses winget)", variable=self.v_apps,
                       bg=BG, font=(F, 10)).grid(row=5, column=0, columnspan=2, sticky="w", pady=6)
        tk.Label(df, text="Detective Duck checks Windows Defender, the firewall, Windows Update and your apps. "
                          "He only reports: scans, definition updates and app updates run when you press their buttons.",
                 bg=BG, fg="#444444", font=(F, 9), justify="left", wraplength=460).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))

        cf = frames["Cleanup"]
        tk.Label(cf, text="Cleanup Crew always shows you what it found and asks before changing anything. "
                          "Downloads tidying only moves files into Images, Documents, Installers, Archives, "
                          "Videos and Audio folders, and can be undone.",
                 bg=BG, fg="#444444", font=(F, 9), justify="left", wraplength=460).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

        gf = frames["General"]
        tk.Checkbutton(gf, text="Play with desktop icons on his own", variable=d.icon_play,
                       bg=BG, font=(F, 10)).grid(row=0, column=0, columnspan=2, sticky="w", pady=4)
        tk.Label(gf, text="Ask Claude model", bg=BG, font=(F, 10)).grid(row=1, column=0, sticky="w", pady=4)
        self.v_model = tk.StringVar(win, value=load_config().get("model", DEFAULT_MODEL))
        tk.Entry(gf, textvariable=self.v_model, width=22, font=(F, 10)).grid(row=1, column=1, sticky="w", padx=8)
        styled_button(gf, "Change API key...", lambda: d.ask.api_key(force=True)).grid(
            row=2, column=0, sticky="w", pady=10)

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        styled_button(bar, "Save", self.save).pack(side="right")
        styled_button(bar, "Cancel", self.close, bg="#9a948a", active="#7f7a72").pack(side="right", padx=6)

    def test(self):
        self.test_lbl.config(text="Reading sensors...")

        def done(r):
            if self.win is None:
                return
            if isinstance(r, Exception):
                self.test_lbl.config(text=f"Error: {r}")
                return
            parts = [f"{k.upper()} {r[k]:.0f}°C" for k in ("cpu", "gpu") if r.get(k) is not None]
            self.test_lbl.config(text=("  ·  ".join(parts) + f"   (from {r['source']})") if parts else
                                 "No temperatures found yet. Follow the steps above, then test again.")
        self.duck.run_bg(self.duck.sensors.read, done)

    def save(self):
        from tkinter import messagebox
        new = {}
        for key, v in self.vars.items():
            try:
                val = float(v.get())
                if val < 0:
                    raise ValueError
                new[key] = int(val) if val == int(val) else val
            except ValueError:
                messagebox.showerror("Settings", f"'{v.get()}' isn't a valid number.", parent=self.win)
                return
        new["det_app_updates"] = bool(self.v_apps.get())
        new["model"] = self.v_model.get().strip() or DEFAULT_MODEL
        new["icon_play"] = bool(self.duck.icon_play.get())
        cfg = load_config()
        cfg.update(new)
        save_config(cfg)
        self.duck.cfg = cfg
        self.duck.settings_changed()
        self.close()

    def close(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = None


# ------------------------------------------------------------------ the duck
R = random.randint
DURATIONS = {
    "idle": lambda: R(40, 130), "walk": lambda: R(70, 220), "peck": lambda: 22 * R(2, 4),
    "look": lambda: R(60, 110), "quack": lambda: 50, "flap": lambda: 48,
    "dance": lambda: 110, "sleep": lambda: R(330, 660), "chase": lambda: 450,
    "flee": lambda: 32, "land": lambda: 10, "disco": lambda: 14 + 9 * 18,
    "think": lambda: 4000, "perch": lambda: R(150, 320), "icon_peck": lambda: 22 * R(3, 5),
    "grab": lambda: 30,
}
FOREVER = 10 ** 9
CALM = {"idle", "walk", "peck", "look", "dance", "chase"}
AIRBORNE = {"fall", "hop", "drag", "fly"}
BUSY = AIRBORNE | {"perch", "icon_peck", "grab"}   # not standing on the taskbar


class Duck:
    def __init__(self):
        root = self.root = tk.Tk()
        root.title("Peking Duck")
        root.overrideredirect(True)
        root.wm_attributes("-topmost", True)

        S = self.S = SCALE or auto_scale()
        self.spr_w, self.spr_h = (GW + 2) * S, (GH + 2) * S
        self.win_w, self.win_h = self.spr_w + 40 * S, self.spr_h + 22 * S
        self.sx = (self.win_w - self.spr_w) // 2      # sprite position inside window
        self.sy = self.win_h - self.spr_h

        bg = KEY
        if IS_WIN:
            root.wm_attributes("-transparentcolor", KEY)
        elif IS_MAC:
            bg = "systemTransparent"
            root.wm_attributes("-transparent", True)
        root.config(bg=bg)
        self.canvas = tk.Canvas(root, width=self.win_w, height=self.win_h, bg=bg,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.font = ("Segoe UI" if IS_WIN else "Helvetica", 10, "bold")

        self.mons = monitors(root)
        self.vtop = min(m.wt for m in self.mons)
        self.set_monitor(random.choice(self.mons))

        self.cache = {}
        gs = max(2, S * 3 // 4)
        self.glyphs = {k: build_image(stamp({}, rows), len(rows[0]), len(rows), gs)
                       for k, rows in GLYPHS.items()}
        self.sprite = self.canvas.create_image(self.sx, self.sy, anchor="nw")
        self.bubble_items, self.bubble_t = None, 0
        self.particles = []
        self.ball_items = None

        self.x = random.uniform(self.minx, self.maxx)
        self.y = float(self.wt)
        self.vx = self.vy = 0.0
        self.waypoints = []
        self.facing = random.choice((-1, 1))
        self.pose, self.bob, self.blink_t = POSE, 0, 0
        self.state, self.ticks, self.t, self.dur = "fall", 0, 0, 0
        self.first_landing = True
        self.px, self.py = root.winfo_pointerxy()
        self.pspeed, self.pdx, self.pdist = 0.0, 0.0, 9999.0
        self.hovering, self.hover_ticks, self.away = False, 0, 0
        self.pressed, self.press_at, self.grab = False, (0, 0), (0, 0)
        self.pokes = []
        self.click_job = None
        self.ask = AskClaude(self)
        self.fly_then = None
        self.desk = DesktopIcons()
        self.icon, self.icon_plan, self.carrying, self.jiggled = None, None, False, False
        self.icon_play = tk.BooleanVar(root, value=load_config().get("icon_play", True))
        self.restore_pending_icon()
        atexit.register(self.at_exit)
        self.cfg = load_config()
        self.mode, self.heat, self.temps, self.hottest = None, None, None, ("PC", 0)
        self.jit = 0
        self.jobs = queue.Queue()
        self.sensors = Sensors(lambda: self.opt("lhm_port"))
        self.health_busy, self.health_last, self.last_announce, self.last_hot_alert = False, 0.0, 0.0, 0.0
        self.warned_unknown = False
        self.det_busy, self.det_next, self.case_report = False, None, None
        self.clean_busy = False
        self.busy_text, self.busy_since = "", 0.0
        self.case, self.cleanup, self.settings = CaseFile(self), CleanupWindow(self), SettingsWindow(self)
        self.mode_var = tk.StringVar(root, value="")

        c = self.canvas
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_motion)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Double-Button-1>", self.on_double)
        c.bind("<Button-3>", self.on_menu)
        if IS_MAC:
            c.bind("<Button-2>", self.on_menu)

        m = self.menu = tk.Menu(root, tearoff=0)
        m.add_command(label="Ask Claude...", command=self.open_ask)
        m.add_separator()
        hm = tk.Menu(m, tearoff=0)
        hm.add_checkbutton(label="Health monitor mode", variable=self.mode_var, onvalue="health",
                           offvalue="", command=self.apply_mode)
        hm.add_command(label="Show temperatures", command=self.show_temps)
        m.add_cascade(label="Health monitor", menu=hm)
        dm = tk.Menu(m, tearoff=0)
        dm.add_checkbutton(label="Detective mode", variable=self.mode_var, onvalue="detective",
                           offvalue="", command=self.apply_mode)
        dm.add_command(label="Investigate now", command=self.investigate)
        dm.add_command(label="Quick virus scan", command=self.quick_scan)
        dm.add_command(label="Update virus definitions", command=self.update_definitions)
        dm.add_command(label="Open case file", command=self.show_case_file)
        m.add_cascade(label="Detective", menu=dm)
        cm = tk.Menu(m, tearoff=0)
        cm.add_checkbutton(label="Cleanup crew mode", variable=self.mode_var, onvalue="cleanup",
                           offvalue="", command=self.apply_mode)
        cm.add_command(label="Clean up...", command=self.open_cleanup)
        cm.add_command(label="Undo last Downloads tidy", command=self.undo_tidy)
        m.add_cascade(label="Cleanup crew", menu=cm)
        m.add_separator()
        fm = tk.Menu(m, tearoff=0)
        for label, st in (("Disco!", "disco"), ("Go for a flight", "fly"),
                          ("Quack", "quack"), ("Waddle around", "walk"),
                          ("Peck for snacks", "peck"), ("Flap!", "flap"),
                          ("Dance", "dance"), ("Take a nap", "sleep"), ("Come here", "chase")):
            fm.add_command(label=label, command=lambda s=st: self.set_state(s))
        fm.add_command(label="Visit another screen", command=lambda: self.start_roam(True))
        m.add_cascade(label="Do something", menu=fm)
        if IS_WIN:
            im = tk.Menu(m, tearoff=0)
            im.add_command(label="Perch on one", command=lambda: self.start_icon("visit", True))
            im.add_command(label="Peck one", command=lambda: self.start_icon("peck", True))
            im.add_command(label="Borrow one (he puts it back)",
                           command=lambda: self.start_icon("steal", True))
            im.add_separator()
            im.add_checkbutton(label="Play with icons on his own", variable=self.icon_play,
                               command=self.save_icon_pref)
            m.add_cascade(label="Desktop icons", menu=im)
        m.add_separator()
        m.add_command(label="Settings...", command=self.open_settings)
        m.add_command(label="Fly away (quit)", command=self.quit)

        hide_from_alt_tab(root)
        root.geometry(f"{self.win_w}x{self.win_h}+{int(self.x)}+{int(self.y)}")
        self.set_state("fall")
        root.after(TICK_MS, self.tick)

    # ---------------------------------------------------------- state control
    def set_state(self, name, text=None, dur=None, waypoints=None, then=None):
        if self.state == "disco" and name != "disco":
            self.remove_disco_ball()
        if self.carrying and name != "fly":
            self.restore_icon()                    # interrupted mid-carry: put it back
            text = text or "Fine, I'll put it back!"
        elif self.state == "icon_peck" and name != "icon_peck":
            self.restore_icon()                    # undo any peck wobble
        self.fly_then = then
        self.state, self.t = name, 0
        self.dur = dur if dur is not None else DURATIONS.get(name, lambda: FOREVER)()
        if name == "quack":
            self.say(text or random.choice(QUACKS))
        elif name == "flee":
            self.facing = -1 if self.pdx > 0 else 1
            self.say(text or random.choice(["Eek!", "QUACK!", "Whoa!"]), 40)
        elif name == "hop":
            self.vy = -2.6 * self.S
            self.say(text or random.choice(QUACKS), 45)
        elif name == "fall":
            self.vy = 0.0
        elif name == "drag":
            if random.random() < 0.5:
                self.say(random.choice(["Put me down!", "Wheee!", "Where are we going?"]), 50)
        elif name == "walk":
            if random.random() < 0.4:
                self.facing *= -1
        elif name == "pet":
            self.away = 0
            if self.mode == "health":
                self.say(self.readout(), 80)
        elif name == "disco":
            self.say(text or random.choice(["Let's boogie!", "Hit it!", "Disco time!"]), 45)
            self.add_disco_ball()
        elif name == "fly":
            if waypoints is not None:
                if text:
                    self.say(text, 45)
                self.waypoints = list(waypoints)
            else:
                self.say(text or random.choice(["Up, up and away!", "Duck patrol!", "Wheee!"]), 45)
                self.waypoints = self.random_waypoints(R(3, 5))
                m = random.choice(self.mons)
                self.waypoints.append((random.uniform(*self.span_x(m)), m.wb - self.win_h - 20 * self.S))
            if self.y >= self.ground - 2:              # taking off from the taskbar
                self.vx, self.vy = 0.0, -3.0 * self.S
        elif text:
            self.say(text)

    def span_x(self, m):
        """Range of window x positions that keep the duck on monitor m."""
        return m.wl - self.sx, max(m.wl - self.sx, m.wr - self.sx - self.spr_w)

    def random_waypoints(self, n):
        """Random sky points spread across all monitors."""
        pts = []
        for _ in range(n):
            m = random.choice(self.mons)
            top = m.wt + 10 * self.S
            bottom = max(top + 1, m.wb - self.win_h - 40 * self.S)
            pts.append((random.uniform(*self.span_x(m)), random.uniform(top, bottom)))
        return pts

    def choose_next(self):
        opts = [("walk", 30), ("idle", 16), ("peck", 12), ("look", 8),
                ("quack", 6), ("flap", 5), ("dance", 4), ("sleep", 3),
                ("disco", 3), ("fly", 3)]
        pm = self.monitor_at_point(self.px, self.py)
        if self.py > pm.wb - 450 and (pm != self.mon or self.spr_w < abs(self.pdx) < 900):
            opts.append(("chase", 12 if pm == self.mon else 5))
        if len(self.mons) > 1:
            opts.append(("roam", 4))
        if self.icon_play.get() and self.desk.lv:
            opts += [("icon_visit", 3), ("icon_peck", 2), ("icon_steal", 2)]
        names, weights = zip(*opts)
        nxt = random.choices(names, weights)[0]
        if nxt.startswith("icon_"):
            self.start_icon(nxt[5:])
        elif nxt == "roam":
            self.start_roam()
        else:
            self.set_state(nxt)

    # ---------------------------------------------------------- monitors
    def set_monitor(self, m):
        """Make m the screen he's on: its taskbar is his ground and its edges his walls."""
        self.mon = m
        self.wl, self.wt, self.wr, self.wb = m.wl, m.wt, m.wr, m.wb
        self.ground = self.wb - self.win_h
        self.minx, self.maxx = self.span_x(m)

    def monitor_at_point(self, x, y):
        for m in self.mons:
            if m.l <= x < m.r and m.t <= y < m.b:
                return m

        def dist(m):
            dx = max(m.l - x, 0, x - m.r + 1)
            dy = max(m.t - y, 0, y - m.b + 1)
            return dx * dx + dy * dy
        return min(self.mons, key=dist)

    def monitor_below(self):
        """The screen he'd land on if he dropped straight down from where he is."""
        cx, bottom = self.x + self.sx + self.spr_w / 2, self.y + self.win_h
        col = [m for m in self.mons if m.l <= cx < m.r]
        if not col:
            return min(self.mons, key=lambda m: min(abs(cx - m.l), abs(cx - m.r)))
        below = [m for m in col if m.wb >= bottom - 4]
        return min(below, key=lambda m: m.wb) if below else max(col, key=lambda m: m.wb)

    def cross(self, direction):
        """Walked into a screen edge: step onto the neighbouring monitor if there is one,
        dropping down or hopping up when its taskbar sits at a different height."""
        m = self.mon
        edge = m.l if direction < 0 else m.r
        nbrs = [n for n in self.mons if n != m and n.t < m.b and n.b > m.t
                and abs((n.r if direction < 0 else n.l) - edge) <= 4]
        if not nbrs:
            return False
        self.set_monitor(min(nbrs, key=lambda n: abs(n.wb - m.wb)))
        if self.ground > self.y + 2:
            self.set_state("fall")
        elif self.ground < self.y - 2:
            self.set_state("hop", text=random.choice(["Hup!", "Up we go!"]))
            self.vy = -math.sqrt(2 * 0.25 * self.S * (self.y - self.ground + 8 * self.S))
        return True

    def refresh_monitors(self):
        mons = monitors(self.root)
        if mons == self.mons:
            return
        self.mons = mons
        self.vtop = min(m.wt for m in mons)
        if self.mon in mons:
            return
        self.set_monitor(self.monitor_below())    # his screen went away
        if self.state not in BUSY:
            self.set_state("fall")

    def start_roam(self, manual=False):
        others = [m for m in self.mons if m != self.mon]
        if not others:
            self.set_state("quack" if manual else "idle",
                           text="There's only one screen!" if manual else None)
            return
        m = random.choice(others)
        self.set_state("fly", text=random.choice(["Road trip!", "What's over there?", "Changing screens!"]),
                       waypoints=[(random.uniform(*self.span_x(m)), m.wb - self.win_h - 20 * self.S)])

    # ---------------------------------------------------------- desktop icon play
    def perch_point(self, ic):
        """Window position that puts the duck's feet on top of the icon."""
        return (ic.left + ic.w / 2 - self.sx - self.spr_w / 2, ic.top - self.win_h + self.S)

    def start_icon(self, plan, manual=False):
        icons = [ic for ic in self.desk.icons()
                 if self.desk.visible(ic) and ic.top - self.spr_h
                 >= self.monitor_at_point(ic.left + ic.w // 2, ic.top).wt - 4 * self.S]
        if plan == "steal" and not self.desk.movable:
            icons = []
        if not icons:
            if manual:
                msg = ("Auto-arrange is on, so I can't move icons."
                       if plan == "steal" and not self.desk.movable and self.desk.lv
                       else "I can't see any icons. Show me the desktop!")
                self.set_state("quack", text=msg)
            else:
                self.set_state("idle")
            return
        self.icon, self.icon_plan = random.choice(icons), plan
        text = {"visit": "Ooh, what's that?", "peck": "Snack time!", "steal": "Ooh, shiny!"}[plan]
        self.set_state("fly", text=text, waypoints=[self.perch_point(self.icon)], then=self.arrive_icon)

    def arrive_icon(self):
        ic = self.icon
        self.set_monitor(self.monitor_at_point(ic.left + ic.w // 2, ic.top + ic.h // 2))
        self.x, self.y = self.perch_point(ic)
        self.vx = self.vy = 0.0
        if self.icon_plan == "peck":
            if self.desk.movable:
                self.save_pending(self.icon)
            self.set_state("icon_peck")
        elif self.icon_plan == "steal":
            self.set_state("grab", text="Mine!")
        else:
            self.set_state("perch")

    def return_icon(self):
        ic = self.icon
        self.set_monitor(self.monitor_at_point(ic.left + ic.w // 2, ic.top + ic.h // 2))
        self.x, self.y = self.perch_point(ic)
        self.vx = self.vy = 0.0
        self.restore_icon()
        self.set_state("perch", dur=90,
                       text=random.choice(["Put it back. Mostly.", "Just borrowing!", "Good as new."]))

    def leave_icon(self, text=None):
        self.set_state("hop", text=text or random.choice(["Wheee!", "Back to the taskbar!"]))

    def icon_follow(self):
        ic = self.icon
        try:
            self.desk.move_screen(ic, self.x + self.sx + self.spr_w / 2 - ic.w / 2,
                                  self.y + self.win_h - 2 * self.S)
        except Exception:
            self.carrying = False

    def restore_icon(self):
        if self.icon is not None and self.desk.lv:
            try:
                self.desk.restore(self.icon)
            except Exception:
                pass
        self.carrying = False
        self.clear_pending()

    def save_pending(self, ic):
        cfg = load_config()
        cfg["pending_icon"] = [ic.index, ic.px, ic.py]
        save_config(cfg)

    def clear_pending(self):
        cfg = load_config()
        if "pending_icon" in cfg:
            del cfg["pending_icon"]
            save_config(cfg)

    def restore_pending_icon(self):
        p = load_config().get("pending_icon")
        if p and self.desk.ok:              # left over from a crash/forced close
            try:
                self.desk.set_pos(*p)
                self.clear_pending()
            except Exception:
                pass

    def save_icon_pref(self):
        cfg = load_config()
        cfg["icon_play"] = bool(self.icon_play.get())
        save_config(cfg)

    def at_exit(self):
        if self.carrying or self.state == "icon_peck":
            self.restore_icon()
        self.desk.close()

    def quit(self):
        self.at_exit()
        self.root.destroy()

    # ---------------------------------------------------------- main loop
    def tick(self):
        try:
            self.ticks += 1
            if self.ticks % 300 == 0:
                self.refresh_monitors()            # screens plugged in / unplugged / rearranged
            self.read_pointer()
            if self.state in CALM:
                if self.pspeed > 10 * self.S and self.pdist < self.spr_w * 1.1:
                    self.set_state("flee")
                elif self.hover_ticks > 25:
                    self.set_state("pet")
            self.process_jobs()                    # results from background checks
            self.mode_timers()
            self.bob = 0
            getattr(self, "st_" + self.state)()
            self.mode_effects()
            self.t += 1
            self.render()
            self.update_particles()
            self.root.geometry(f"+{int(self.x)}+{int(self.y)}")
            if self.ticks % 100 == 0:          # stay above the taskbar / other windows
                self.root.attributes("-topmost", True)
                self.root.lift()
        except tk.TclError:
            return                              # window was closed
        self.root.after(TICK_MS, self.tick)

    def read_pointer(self):
        px, py = self.root.winfo_pointerxy()
        self.pspeed = math.hypot(px - self.px, py - self.py)
        self.px, self.py = px, py
        left, top = self.x + self.sx, self.y + self.sy
        self.hovering = (left <= px <= left + self.spr_w and
                         top + (Y0 + 2) * self.S <= py <= top + self.spr_h)
        if not self.hovering:
            self.hover_ticks = 0
        elif self.pspeed < 6:
            self.hover_ticks += 1
        cx, cy = left + self.spr_w / 2, top + self.spr_h / 2
        self.pdx = px - cx
        self.pdist = math.hypot(px - cx, py - cy)

    def blinking(self):
        if self.blink_t > 0:
            self.blink_t -= 1
            return True
        if random.random() < 0.012:
            self.blink_t = 4
        return False

    def walk_step(self, mult=1.0, anim=5):
        """Walk one frame. Returns True if he stepped onto another screen and had to
        hop up or drop down (the caller should stop for this frame)."""
        state = self.state
        self.x += self.facing * WALK_SPEED * self.S * mult
        if self.facing < 0 and self.x <= self.minx:
            if not self.cross(-1):
                self.x, self.facing = self.minx, 1
        elif self.facing > 0 and self.x >= self.maxx:
            if not self.cross(1):
                self.x, self.facing = self.maxx, -1
        if self.state != state:
            return True
        phase = (self.t // anim) % 4
        head = "blink" if self.blinking() else "normal"
        self.pose = (head, ("walk1", "stand", "walk2", "stand")[phase], None, 0, 0, 0)
        if phase % 2:
            self.bob = -(self.S // 2)
        return False

    # ---------------------------------------------------------- behaviours
    def st_idle(self):
        self.pose = ("blink" if self.blinking() else "normal", "stand", None, 0, 0, 0)
        if self.pdist < 350 and abs(self.pdx) > 10 and self.t % 10 == 0:
            self.facing = 1 if self.pdx > 0 else -1     # keep an eye on the cursor
        if self.t >= self.dur:
            self.choose_next()

    def st_walk(self):
        if self.walk_step():
            return
        if self.t >= self.dur or random.random() < 0.003:
            self.choose_next()

    def st_look(self):
        self.pose = ("blink" if self.blinking() else "normal", "stand", None, 0, 0, 0)
        if self.t % 25 == 24 and random.random() < 0.7:
            self.facing *= -1
        if self.t >= self.dur:
            self.choose_next()

    def st_peck(self):
        down = 6 <= self.t % 22 < 13
        self.pose = ("normal", "stand", None, 3, 9, 0) if down else POSE
        if self.t >= self.dur:
            self.choose_next()

    def st_quack(self):
        open_ = self.t < 24 and (self.t // 6) % 2 == 0
        self.pose = ("quack" if open_ else "normal", "stand", None, 0, 0, 0)
        if self.t >= self.dur:
            self.set_state("idle")

    def st_flap(self):
        self.pose = ("quack" if self.t < 10 else "normal", "stand",
                     "up" if (self.t // 3) % 2 == 0 else None, 0, 0, 0)
        self.bob = -int(abs(math.sin(self.t * 0.26)) * self.S * 4)
        if self.t >= self.dur:
            self.choose_next()

    def st_dance(self):
        beat = self.t // 7
        self.facing = 1 if (self.t // 21) % 2 == 0 else -1
        self.pose = ("quack" if beat % 4 == 0 else "normal",
                     "walk1" if beat % 2 else "walk2",
                     "up" if beat % 3 == 0 else None, 0, 0, 0)
        self.bob = -self.S * (beat % 2)
        if self.t % 16 == 0:
            hx, hy = self.head_pos()
            self.spawn("note", hx + R(-25, 25), hy, random.uniform(-0.5, 0.5), -1.0, 45)
        if self.t >= self.dur:
            self.choose_next()

    def st_disco(self):
        t = self.t
        if t < 14:                                 # wind-up before standing tall
            self.pose = ("quack" if t < 8 else "normal", "stand", None, 0, 0, 0)
            self.bob = -self.S if t > 8 else 0
        else:
            beat = (t - 14) // 9
            self.facing = 1 if (beat // 4) % 2 == 0 else -1
            if beat % 2 == 0:                      # wing pointed to the sky
                self.pose = ("quack" if beat % 4 == 0 else "normal", "tall1", "disco_up", 0, 0, 0)
            else:                                  # wing down, hip kick
                self.pose = ("blink" if beat % 8 == 3 else "normal", "tall2", "disco_down", 0, 0, 0)
            self.bob = -self.S if beat % 2 else 0
        if t % 5 == 0:
            self.spawn(random.choice(("spark_p", "spark_c", "spark_y")),
                       R(10, self.win_w - 10), R(14 * self.S, self.sy + self.spr_h // 2),
                       0, random.uniform(-0.3, 0.3), 16)
        if self.ball_items and t % 6 == 0:          # spin the disco ball
            self.canvas.itemconfig(self.ball_items[1],
                                   image=self.glyphs["ball"] if (t // 6) % 2 else self.ball_alt)
        if t >= self.dur:
            self.set_state("quack", text=random.choice(["Disco duck!", "Thank you, thank you.",
                                                        "Quack-tastic!"]))

    def st_fly(self):
        if not self.waypoints or self.t > 1500:
            if self.waypoints or not self.fly_then:
                self.set_monitor(self.monitor_below())   # land on whichever screen is under him
                self.set_state("fall")
            else:
                self.fly_then()                    # arrived where we were heading
            return
        tx, ty = self.waypoints[0]
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy) or 1.0
        landing = len(self.waypoints) == 1 and self.fly_then is not None
        sp = 2.4 * self.S
        if landing:                                # ease in for a precise touchdown
            sp = min(sp, max(0.8 * self.S, dist * 0.12))
        self.vx += (dx / dist * sp - self.vx) * (0.12 if landing else 0.06)
        self.vy += (dy / dist * sp - self.vy) * (0.12 if landing else 0.06)
        self.x += self.vx
        self.y = max(self.vtop - self.sy, self.y + self.vy)
        if dist < (3 if landing else 10) * self.S:
            self.waypoints.pop(0)
        if abs(self.vx) > 0.4:
            self.facing = 1 if self.vx > 0 else -1
        flap = (self.t // 4) % 2 == 0
        self.pose = ("quack" if self.t < 12 else "normal", "dangle1" if self.carrying else None,
                     "up" if flap else "down", 0, 0, 0)
        if self.carrying:
            self.icon_follow()

    def st_perch(self):
        self.pose = ("blink" if self.blinking() else "normal", "stand", None, 0, 0, 0)
        if self.t % 60 == 59 and random.random() < 0.5:
            self.facing *= -1
        if self.t == 45 and self.bubble_t <= 0 and random.random() < 0.6:
            self.say(random.choice(["Nice view up here.", "King of the desktop!", "Comfy."]))
        if self.t >= self.dur:
            self.leave_icon()

    def st_icon_peck(self):
        c = self.t % 22
        self.pose = ("normal", "stand", None, 3, 9, 0) if 6 <= c < 13 else POSE
        if self.desk.movable and c in (7, 10):     # each peck knocks the icon down a little
            try:
                if c == 7:
                    self.desk.set_pos(self.icon.index, self.icon.px, self.icon.py + 2 * self.S)
                else:
                    self.desk.restore(self.icon)
            except Exception:
                pass
        if self.t >= self.dur:
            self.leave_icon(random.choice(["Tasty pixels.", "Crunchy!", "Needs salt."]))

    def st_grab(self):
        flap = (self.t // 3) % 2 == 0
        self.pose = ("quack" if self.t < 12 else "normal", "dangle1", "up" if flap else None, 0, 0, 0)
        self.bob = -(self.t // 6) * self.S // 2
        if self.t >= self.dur:
            self.save_pending(self.icon)
            self.carrying = True
            pts = self.random_waypoints(R(2, 3)) + [self.perch_point(self.icon)]
            self.set_state("fly", text=random.choice(["Wheee!", "You'll get it back!", "Catch me!"]),
                           waypoints=pts, then=self.return_icon)

    def st_sleep(self):
        self.pose = ("blink", None, None, 0, 0, 2)
        if self.t % 45 == 10:
            hx, hy = self.head_pos()
            self.spawn("z", hx, hy, 0.4 * self.facing, -0.8, 70)
        if self.t >= self.dur:
            self.set_state("quack", text="*yawn*")

    def st_think(self):
        self.pose = ("blink" if self.blinking() else "normal", "stand", None, 0, 0, 0)
        if self.t % 15 == 0:
            self.say("Hmm" + "." * (1 + (self.t // 15) % 3), 16)
        if self.t >= self.dur:
            self.set_state("idle")

    def st_chase(self):
        pm = self.monitor_at_point(self.px, self.py)
        if pm != self.mon:                         # cursor is on another screen: fly over
            self.set_state("fly", text="Wait for me!", waypoints=[
                (self.px - self.sx - self.spr_w / 2, pm.wb - self.win_h - 20 * self.S)])
            return
        dx = (self.px - self.sx - self.spr_w / 2) - self.x
        if abs(dx) < self.spr_w * 0.35:
            self.set_state("quack", text=random.choice(["Hi!", "Quack?", "Got bread?", "Whatcha doing?"]))
            return
        self.facing = 1 if dx > 0 else -1
        if self.walk_step(1.7, anim=3):
            return
        if self.t > self.dur or self.py < self.wb - 500:
            self.set_state("idle")

    def st_flee(self):
        if self.walk_step(3.0, anim=2):
            return
        self.pose = self.pose[:2] + ("up" if (self.t // 3) % 2 == 0 else None,) + self.pose[3:]
        if self.t >= self.dur:
            self.set_state("idle")

    def st_pet(self):
        self.pose = ("blink", "stand", None, 0, 0, 0)
        self.bob = -self.S if (self.t // 8) % 2 else 0
        if self.t % 14 == 0:
            hx, hy = self.head_pos()
            self.spawn("heart", hx + R(-12, 12), hy, random.uniform(-0.4, 0.4), -1.2, 40)
        self.away = 0 if self.hovering else self.away + 1
        if self.away > 12:
            self.hover_ticks = 0
            self.set_state("quack", text=random.choice(["♥", "Quack ♥", "More pets pls"]))

    def st_drag(self):
        self.set_monitor(self.monitor_at_point(self.px, self.py))
        self.x = self.px - self.grab[0]
        self.y = min(self.py - self.grab[1], self.ground)
        flap = (self.t // 4) % 2 == 0
        self.pose = ("quack" if (self.t // 20) % 3 == 0 else "normal",
                     "dangle1" if (self.t // 6) % 2 == 0 else "dangle2",
                     "up" if flap else None, 0, 0, 0)

    def st_fall(self):
        self.vy = min(self.vy + 0.18 * self.S, 6 * self.S)
        self.y += self.vy
        target = min(max(self.x, self.minx), self.maxx)   # drift back over the taskbar
        self.x += (target - self.x) * 0.15
        flap = (self.t // 3) % 2 == 0
        self.pose = ("quack" if (self.t // 10) % 2 == 0 else "normal",
                     "dangle1" if flap else "dangle2", "up" if flap else None, 0, 0, 0)
        if self.y >= self.ground:
            self.y, self.vy = self.ground, 0.0
            self.x = min(max(self.x, self.minx), self.maxx)
            self.set_state("land")

    def st_land(self):
        self.pose = ("blink", None, None, 0, 0, 2)
        if self.t >= self.dur:
            if self.first_landing:
                self.first_landing = False
                self.set_state("quack", text="Peking Duck has landed!")
            elif random.random() < 0.6:
                self.set_state("quack", text=random.choice(["Oof.", "Hmph.", "Again! Again!", "Nailed it."]))
            else:
                self.set_state("idle")

    def st_hop(self):
        self.vy += 0.25 * self.S
        self.y += self.vy
        target = min(max(self.x, self.minx), self.maxx)
        self.x += (target - self.x) * 0.1
        self.pose = ("quack" if self.t < 14 else "normal", "dangle1",
                     "up" if (self.t // 3) % 2 == 0 else None, 0, 0, 0)
        if self.vy > 0 and self.y >= self.ground:
            self.y, self.vy = self.ground, 0.0
            self.set_state("idle", dur=40)

    # ---------------------------------------------------------- disco ball
    def add_disco_ball(self):
        self.remove_disco_ball()
        if not hasattr(self, "ball_alt"):           # mirrored ball = "spinning" frame
            rows = GLYPHS["ball"]
            self.ball_alt = build_image(stamp({}, rows), len(rows[0]), len(rows),
                                        max(2, self.S * 3 // 4), mirror=True)
        cx = self.win_w // 2
        line = self.canvas.create_line(cx, 0, cx, 6 * self.S, fill=OUTLINE, width=2)
        ball = self.canvas.create_image(cx, 6 * self.S, image=self.glyphs["ball"], anchor="n")
        self.ball_items = (line, ball)

    def remove_disco_ball(self):
        if self.ball_items:
            for i in self.ball_items:
                self.canvas.delete(i)
        self.ball_items = None

    # ---------------------------------------------------------- mouse
    def on_press(self, e):
        self.pressed = True
        self.press_at = (e.x_root, e.y_root)
        self.grab = (e.x_root - self.x, e.y_root - self.y)

    def on_motion(self, e):
        if self.pressed and self.state != "drag":
            if math.hypot(e.x_root - self.press_at[0], e.y_root - self.press_at[1]) > 6:
                self.set_state("drag")

    def on_release(self, e):
        if not self.pressed:
            return
        self.pressed = False
        if self.state == "drag":
            self.set_state("fall")
            return
        # wait a moment so a double-click can open Ask Claude instead
        self.click_job = self.root.after(260, self.single_click)

    def single_click(self):
        self.click_job = None
        self.pokes = [t for t in self.pokes if self.ticks - t < 50] + [self.ticks]
        if len(self.pokes) >= 3:
            self.pokes = []
            if self.state not in AIRBORNE:
                self.set_state("flee", text="Stop poking me!")
        elif self.state == "sleep":
            self.set_state("hop", text="Huh?! I'm up!")
        elif self.state in AIRBORNE:
            self.say(random.choice(["Quack!", "I'm busy flying!"]), 35)
        else:
            self.set_state("hop")

    def on_double(self, e):
        if self.click_job:
            self.root.after_cancel(self.click_job)
            self.click_job = None
        self.pressed = False
        self.open_ask()

    def open_ask(self):
        self.ask.open()
        if self.state not in BUSY:
            self.set_state("quack", text=random.choice(["Quack? What's up?", "Ask away!"]))

    def react(self, state, text):
        """Change state if he's on the taskbar; otherwise just say it where he is."""
        if self.state in BUSY:
            self.say(text, 45)
        else:
            self.set_state(state, text=text)

    def on_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    # ---------------------------------------------------------- drawing
    def head_pos(self):
        _, _, _, hx, hy, by = self.pose
        if is_tall(self.pose):
            gx, gy = 10 + hx + 5, 2 + hy + 1 + TOP
        else:
            gx, gy = 11 + hx + 5, Y0 + hy + by + 1 + TOP
        if self.facing < 0:
            gx = GW + 2 - gx
        return self.sx + gx * self.S, self.sy + gy * self.S + self.bob

    def render(self):
        look = self.current_look()
        key = (self.pose, self.facing, look)
        img = self.cache.get(key)
        if img is None:
            img = self.cache[key] = build_image(compose(self.pose, look), GW, GH, self.S, self.facing < 0)
        self.canvas.itemconfig(self.sprite, image=img)
        self.canvas.coords(self.sprite, self.sx + self.jit, self.sy + self.bob)
        self.render_bubble()

    def say(self, text, ticks=55):
        self.clear_bubble()
        self.bubble_text, self.bubble_t = text, ticks

    def clear_bubble(self):
        if self.bubble_items:
            for i in self.bubble_items:
                self.canvas.delete(i)
        self.bubble_items = None

    def render_bubble(self):
        if self.bubble_t <= 0:
            self.clear_bubble()
            return
        self.bubble_t -= 1
        c = self.canvas
        if not self.bubble_items:
            tail = c.create_polygon(0, 0, 0, 0, 0, 0, fill="white", outline=OUTLINE, width=2)
            rect = c.create_rectangle(0, 0, 1, 1, fill="white", outline=OUTLINE, width=2)
            txt = c.create_text(0, 0, text=self.bubble_text, font=self.font, fill="#1a1a1a",
                                width=self.win_w - 30, justify="center")
            self.bubble_items = (tail, rect, txt)
        tail, rect, txt = self.bubble_items
        x1, y1, x2, y2 = c.bbox(txt)
        pad = 6
        bw, bh = (x2 - x1) + 2 * pad, (y2 - y1) + 2 * pad
        hx, hy = self.head_pos()
        bx = min(max(hx - bw / 2, 2), self.win_w - bw - 2)
        by = max(2, hy - bh - 12)
        c.coords(rect, bx, by, bx + bw, by + bh)
        c.coords(txt, bx + bw / 2, by + bh / 2)
        tx = min(max(hx, bx + 10), bx + bw - 10)
        c.coords(tail, tx - 6, by + bh - 3, tx + 6, by + bh - 3, hx, by + bh + 9)
        for i in self.bubble_items:
            c.tag_raise(i)

    def spawn(self, kind, x, y, vx, vy, life):
        item = self.canvas.create_image(x, y, image=self.glyphs[kind])
        self.particles.append([item, x, y, vx, vy, life])

    def update_particles(self):
        for p in self.particles[:]:
            p[1] += p[3]
            p[2] += p[4]
            p[5] -= 1
            if p[5] <= 0 or p[2] < 0:
                self.canvas.delete(p[0])
                self.particles.remove(p)
            else:
                self.canvas.coords(p[0], p[1], p[2])

    # ---------------------------------------------------------- helper modes: plumbing
    def opt(self, key):
        return self.cfg.get(key, DEFAULTS.get(key))

    def settings_changed(self):
        if self.mode == "detective":
            hours = float(self.opt("det_auto_hours"))
            self.det_next = time.time() + hours * 3600 if hours > 0 else None
        self.health_last = 0

    def run_bg(self, fn, done):
        """Run fn on a worker thread; done(result or exception) runs back on the duck's thread."""
        def worker():
            try:
                res = fn()
            except Exception as e:
                res = e
            self.jobs.put((done, res))
        threading.Thread(target=worker, daemon=True).start()

    def process_jobs(self):
        while True:
            try:
                done, res = self.jobs.get_nowait()
            except queue.Empty:
                return
            try:
                done(res)
            except tk.TclError:
                pass

    def ensure_mode(self, mode):
        if self.mode != mode:
            self.mode_var.set(mode)
            self.apply_mode()

    def apply_mode(self):
        new = self.mode_var.get() or None
        if new == self.mode:
            return
        self.mode = new
        self.heat, self.temps = None, None
        for _ in range(10):                           # costume-change sparkle "poof"
            self.spawn(random.choice(("spark_p", "spark_c", "spark_y")),
                       self.sx + R(0, self.spr_w), self.sy + R(0, self.spr_h),
                       random.uniform(-1, 1), random.uniform(-1.2, 0.2), 18)
        self.react("quack", {"health": "Dr. Duck is in!", "detective": "Detective Duck, on the case!",
                             "cleanup": "Cleanup crew, reporting!", None: "Back to regular duck."}[new])
        now = time.time()
        if new == "health":
            self.health_last, self.last_announce, self.warned_unknown = 0, now, False
        elif new == "detective":
            hours = float(self.opt("det_auto_hours"))
            self.det_next = now + 3 if hours > 0 else None     # first look-around right away
        elif new == "cleanup":
            self.run_bg(fixed_drives, self.on_drives)

    def mode_timers(self):
        now = time.time()
        if self.mode == "health":
            if not self.health_busy and now - self.health_last >= max(2.0, float(self.opt("health_poll"))):
                self.health_busy, self.health_last = True, now
                self.run_bg(self.sensors.read, self.on_health)
            every = float(self.opt("health_announce"))
            if (every > 0 and self.temps and now - self.last_announce >= every * 60
                    and self.bubble_t <= 0 and self.state not in BUSY):
                self.last_announce = now
                self.say(self.readout(), 90)
            if self.heat == "hot" and now - self.last_hot_alert > 120:
                self.last_hot_alert = now
                self.react("quack", self.hot_line())
        elif self.mode == "detective":
            if self.det_next and now >= self.det_next and not self.det_busy:
                self.investigate(auto=True)

    def current_look(self):
        m = self.mode
        if not m:
            return None
        hat = {"health": "doctor", "detective": "detective", "cleanup": "hardhat"}[m]
        extras = ()
        if m == "health":
            extras = ("doctor_band",) + (("scarf",) if self.heat == "cool" else
                                         ("blush",) if self.heat == "hot" else ())
        prop, pdx, pdy = None, 0, 0
        if m == "detective":
            prop = "magnifier"
            if self.state == "busy":
                pdy = -((self.ticks // 8) % 2)
        elif m == "cleanup":
            prop = "broom"
            if self.state in ("busy", "walk"):
                pdx = (self.ticks // 5) % 2
        return (hat, extras, prop, pdx, pdy)

    def mode_effects(self):
        """Per-frame touches on top of whatever he's doing: sweat, fanning, shivering, dust."""
        self.jit = 0
        still = self.state in ("idle", "look", "perch")
        if self.mode == "health" and self.state in ("idle", "look", "walk", "perch", "pet", "busy"):
            if self.heat in ("warm", "hot"):
                if self.t % (16 if self.heat == "hot" else 40) == 5:
                    hx, hy = self.head_pos()
                    self.spawn("drop", hx + R(-14, 10), hy + 2 * self.S, random.uniform(-0.4, 0.4), 1.0, 22)
                if self.heat == "hot" and still:          # fan himself with a wing
                    self.pose = self.pose[:2] + ("up" if (self.ticks // 4) % 2 else None,) + self.pose[3:]
            elif self.heat == "cool" and still:
                self.jit = 1 if (self.ticks // 2) % 2 else -1
        if self.mode == "cleanup" and self.state in ("walk", "busy") and self.t % 9 == 0:
            gx = 21 if self.facing > 0 else GW + 1 - 21
            self.spawn("dust", self.sx + gx * self.S + R(-6, 6), self.sy + self.spr_h - 2 * self.S,
                       random.uniform(-0.6, 0.6), -0.4, 18)

    def start_busy(self, text):
        self.busy_text, self.busy_since = text, time.time()
        if self.state in BUSY:
            self.say(text + "...", 60)
        else:
            self.set_state("busy")

    def end_busy(self, text):
        if self.state == "busy":
            self.set_state("quack", text=text)
        else:
            self.say(text, 70)

    def st_busy(self):
        if self.walk_step(0.8 if self.mode == "cleanup" else 0.5, anim=7):
            return
        if self.t % 45 == 0:
            s = int(time.time() - self.busy_since)
            self.say(f"{self.busy_text}... {s // 60}:{s % 60:02d}", 44)
        if random.random() < 0.006:
            self.facing *= -1
        if self.t > 3 * 3600 * 33:
            self.set_state("idle")

    # ---------------------------------------------------------- health monitor
    def on_health(self, res):
        self.health_busy = False
        if isinstance(res, Exception) or self.mode != "health":
            return
        self.temps = res
        vals = [(k.upper(), res[k]) for k in ("cpu", "gpu") if res.get(k) is not None]
        if vals:
            self.hottest = max(vals, key=lambda kv: kv[1])
            t = self.hottest[1]
            new = ("hot" if t >= float(self.opt("health_hot")) else
                   "warm" if t >= float(self.opt("health_warm")) else
                   "cool" if t < float(self.opt("health_cool")) else "ok")
        else:
            new = "unknown"
        old, self.heat = self.heat, new
        if new == old:
            return
        name, t = self.hottest if vals else ("", 0)
        if new == "hot":
            self.last_hot_alert = time.time()
            self.react("quack", self.hot_line())
        elif new == "warm":
            self.say(f"Getting toasty... {name} is {t:.0f}°C", 70)
        elif new == "cool":
            self.say("Brr... nice and chilly in here.", 60)
        elif new == "ok" and old in ("hot", "warm"):
            self.say("Phew, cooling down.", 60)
        elif new == "ok" and old is None:
            self.say(self.readout(), 80)
        elif new == "unknown" and not self.warned_unknown:
            self.warned_unknown = True
            self.say("I can't read your temperatures yet. Right-click > Settings > Health for setup.", 120)

    def hot_line(self):
        name, t = getattr(self, "hottest", ("PC", 0))
        return random.choice([f"Whoa! {name} is at {t:.0f}°C!", f"It's a sauna in here! {name} {t:.0f}°C",
                              f"{name} is cooking at {t:.0f}°C!"])

    def readout(self):
        r = self.temps or {}
        parts = []
        if r.get("cpu") is not None:
            load = f" ({r['cpu_load']:.0f}% busy)" if r.get("cpu_load") is not None else ""
            parts.append(f"CPU {r['cpu']:.0f}°C{load}")
        elif r.get("cpu_load") is not None:
            parts.append(f"CPU {r['cpu_load']:.0f}% busy")
        if r.get("gpu") is not None:
            load = f" ({r['gpu_load']:.0f}% busy)" if r.get("gpu_load") is not None else ""
            parts.append(f"GPU {r['gpu']:.0f}°C{load}")
        return "\n".join(parts) if parts else "No temperature readings yet."

    def show_temps(self):
        self.ensure_mode("health")
        if self.temps:
            self.say(self.readout(), 100)
        else:
            self.say("Taking your temperature...", 45)
            self.health_last = 0

    # ---------------------------------------------------------- detective
    def investigate(self, auto=False):
        self.ensure_mode("detective")
        if self.det_busy:
            self.say("Already on the case!", 45)
            return
        self.det_busy = True
        hours = float(self.opt("det_auto_hours"))
        self.det_next = time.time() + hours * 3600 if hours > 0 else None
        self.start_busy("Investigating")
        include = bool(self.opt("det_app_updates"))
        self.run_bg(lambda: investigate_job(include), lambda rep: self.on_investigated(rep, auto))

    def on_investigated(self, rep, auto):
        self.det_busy = False
        if isinstance(rep, Exception):
            self.end_busy("My magnifying glass fogged up. Try again?")
            return
        self.case_report = rep
        n = sum(1 for ok, _ in case_items(rep) if ok is False)
        if n == 0:
            self.end_busy("Case closed: all clear!")
        else:
            self.end_busy(f"Found {n} clue{'s' if n != 1 else ''}!" +
                          (" Right-click > Detective > Open case file" if auto else ""))
        if not auto:
            self.case.show(rep)

    def show_case_file(self):
        if self.case_report:
            self.ensure_mode("detective")
            self.case.show(self.case_report)
        else:
            self.investigate()

    def quick_scan(self):
        self.ensure_mode("detective")
        if self.det_busy:
            self.say("Hang on, I'm still on another case!", 50)
            return
        self.det_busy = True
        self.start_busy("Scanning for suspects")
        self.run_bg(scan_job, self.on_scanned)

    def on_scanned(self, rc):
        self.det_busy = False
        if isinstance(rc, Exception):
            self.end_busy(f"Couldn't scan: {rc}")
            return
        if rc == 0:
            self.end_busy("Case closed: no threats found!")
            return
        self.end_busy("Hmm, something's fishy...")
        from tkinter import messagebox
        if messagebox.askyesno("Detective Duck",
                               f"The quick scan finished with code {rc}. That usually means it found "
                               "something or couldn't finish.\n\nOpen Windows Security to review it?"):
            open_uri("windowsdefender://threat")

    def update_definitions(self):
        self.ensure_mode("detective")
        if self.det_busy:
            self.say("Hang on, I'm still on another case!", 50)
            return
        self.det_busy = True
        self.start_busy("Updating my files")

        def done(rc):
            self.det_busy = False
            if isinstance(rc, Exception) or rc != 0:
                self.end_busy("Couldn't update definitions. Try the Windows Security button.")
            else:
                self.end_busy("Virus definitions are fresh!")
        self.run_bg(defs_job, done)

    def update_apps(self):
        from tkinter import messagebox
        if not messagebox.askyesno("Detective Duck",
                                   "Open a window that updates all your apps with winget?\n\n"
                                   "You'll see its progress there, and Windows may ask permission for some apps."):
            return
        try:
            subprocess.Popen(["cmd", "/k", "winget upgrade --all --accept-package-agreements "
                                           "--accept-source-agreements"], creationflags=0x10)
            self.say("Updating your apps. Watch the black window!", 70)
        except Exception as e:
            self.say(f"Couldn't start winget: {e}", 70)

    # ---------------------------------------------------------- cleanup crew
    def open_cleanup(self):
        self.ensure_mode("cleanup")
        self.cleanup.open()

    def on_drives(self, drives):
        if isinstance(drives, Exception) or self.mode != "cleanup":
            return
        full = [label for label, free, total in drives if total and free / total < 0.10]
        if full:
            self.say(f"{full[0]} is almost full! Right-click > Cleanup crew > Clean up...", 110)

    def start_clean(self, scan, picks, done):
        if self.clean_busy:
            return
        self.clean_busy = True
        self.start_busy("Sweeping")

        def finished(res):
            self.clean_busy = False
            if isinstance(res, Exception):
                self.end_busy("Oops, I tripped over the broom.")
            else:
                if res["moved"]:
                    cfg = load_config()
                    cfg["downloads_undo"] = res["moved"]
                    save_config(cfg)
                self.end_busy(f"Squeaky clean! Freed {human_size(res['freed'])}.")
            done(res)
        self.run_bg(lambda: cleanup_run(scan, *picks), finished)

    def undo_tidy(self):
        log = load_config().get("downloads_undo")
        if not log:
            self.say("Nothing to undo!", 40)
            return

        def done(n):
            if isinstance(n, Exception):
                self.say(f"Couldn't undo: {n}", 70)
                return
            cfg = load_config()
            cfg.pop("downloads_undo", None)
            save_config(cfg)
            self.say(f"Put {n} download{'s' if n != 1 else ''} back where they were.", 70)
            if self.cleanup.win is not None:
                self.cleanup.rescan()
        self.run_bg(lambda: undo_tidy(log), done)

    def open_settings(self):
        self.settings.open()


    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Duck().run()
