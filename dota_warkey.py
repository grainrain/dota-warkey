# -*- coding: utf-8 -*-
"""
DotA 改键精灵 (键盘转键版)  ——  Warcraft III / DotA v6.78 AI 专用
====================================================================
原理：纯键盘转键。你按【自定义键】，程序就把【游戏默认键】发给魔兽。
     这和物品栏、选英雄一个道理，全屏也 100% 有效，不用标定、不动鼠标。

· 技能栏：8 个技能槽，每槽 “自定义键  ->  这个英雄该技能的默认键”
          （默认键看游戏里技能图标 tooltip，例如“穿刺[E]”默认键就是 E）
· 物品栏：按 1-6  ->  发送小键盘 Num7/8/4/5/1/2（魔兽物品栏原生热键）
· 选英雄：按 CapsLock -> 发送 F1
· 方案：不同英雄默认键不同，用“方案”保存多套技能配置，随时切换。
纯 Python 标准库(含 tkinter)，无需安装任何东西。
"""

import ctypes
import ctypes.wintypes as wintypes
import json
import os
import sys
import threading
import time
import queue
import subprocess
import winreg
import winsound
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# ====================================================================
# Win32
# ====================================================================
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1

# 这些键是“扩展键”，扫描码注入时要带 EXTENDEDKEY 标志（默认键位一般用不到，全了更稳）
_EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # PgUp PgDn End Home ← ↑ → ↓
    0x2D, 0x2E,        # Insert Delete
    0x5B, 0x5C, 0x5D,  # LWin RWin Apps
    0xA3, 0xA5,        # 右Ctrl 右Alt
    0x6F, 0x90,        # 小键盘/ NumLock
}
VK_PAUSE = 0x13


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


# 联合体必须含最大成员(MOUSEINPUT)，否则 INPUT 偏小、SendInput 因 cbSize 不符而失败
class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


LPKBDLLHOOKSTRUCT = ctypes.POINTER(KBDLLHOOKSTRUCT)
HOOKPROC = ctypes.CFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def is_elevated():
    """本程序是否以管理员(高完整性)运行。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---- 魔兽“常显血条”开关（改注册表游戏选项，重开魔兽生效，零风险）----
_WAR3_GAMEPLAY = r"Software\Blizzard Entertainment\Warcraft III\Gameplay"


def set_healthbars(on):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WAR3_GAMEPLAY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "healthbars", 0, winreg.REG_DWORD, 1 if on else 0)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def get_healthbars():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WAR3_GAMEPLAY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, "healthbars")
        winreg.CloseKey(key)
        return int(val)
    except Exception:
        return 0


# ====================================================================
# 键名 <-> 虚拟键码
# ====================================================================
_SPECIALS = {
    "SPACE": 0x20, "空格": 0x20, "TAB": 0x09, "ENTER": 0x0D, "回车": 0x0D,
    "ESC": 0x1B, "BACKSPACE": 0x08,
    "CAPSLOCK": 0x14, "CAPS": 0x14, "锁": 0x14,
    "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12,
    "PAUSE": 0x13, "SCROLLLOCK": 0x91,
    "`": 0xC0, "BACKQUOTE": 0xC0, "TILDE": 0xC0,
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE,
    ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22,
}
for _i in range(1, 13):
    _SPECIALS["F%d" % _i] = 0x70 + (_i - 1)
for _i in range(0, 10):
    _SPECIALS["NUMPAD%d" % _i] = 0x60 + _i
    _SPECIALS["NUM%d" % _i] = 0x60 + _i
_SPECIALS["NUM*"] = 0x6A
_SPECIALS["NUM+"] = 0x6B
_SPECIALS["NUM-"] = 0x6D
_SPECIALS["NUM."] = 0x6E
_SPECIALS["NUM/"] = 0x6F


def name_to_vk(name):
    if name is None:
        return None
    n = str(name).strip().upper()
    if not n:
        return None
    if len(n) == 1 and ("A" <= n <= "Z" or "0" <= n <= "9"):
        return ord(n)
    return _SPECIALS.get(n)


def vk_to_name(vk):
    """按键的虚拟码 -> 显示名（用于“点框按键设置”）。"""
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x70 <= vk <= 0x7B:
        return "F%d" % (vk - 0x6F)
    if 0x60 <= vk <= 0x69:
        return "NUMPAD%d" % (vk - 0x60)
    table = {0x20: "空格", 0x14: "CAPSLOCK", 0x0D: "回车", 0x09: "TAB", 0x1B: "ESC",
             0x13: "PAUSE", 0x91: "SCROLLLOCK", 0xC0: "`",
             0xBD: "-", 0xBB: "=", 0xDB: "[", 0xDD: "]", 0xBA: ";", 0xDE: "'",
             0xBC: ",", 0xBE: ".", 0xBF: "/", 0xDC: "\\",
             0x26: "UP", 0x28: "DOWN", 0x25: "LEFT", 0x27: "RIGHT",
             0x2D: "INSERT", 0x2E: "DELETE", 0x24: "HOME", 0x23: "END",
             0x21: "PAGEUP", 0x22: "PAGEDOWN"}
    return table.get(vk)


# ====================================================================
# 配置
# ====================================================================
# 打包成 exe(frozen) 时，__file__ 指向临时解压目录(一关就删)，必须用 exe 的真实位置，
# 否则 config.json 存不住、War3 路径探测也会错。
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOG_PATH = os.path.join(BASE_DIR, "log.txt")


def _bundled_config_path():
    """打包进 exe 的默认 config.json（只读，位于 PyInstaller 临时解压目录 _MEIPASS）。
    exe 旁边没有 config.json 时，就拿它当默认值，从而做到“单文件也能用”。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, "config.json")
        if os.path.exists(p):
            return p
    return None


def icon_path():
    """logo.ico 的位置：打包后在 _MEIPASS 临时目录，源码运行时在程序目录旁。
    标题栏、任务栏都用它当图标。"""
    for base in (getattr(sys, "_MEIPASS", None), BASE_DIR):
        if base:
            p = os.path.join(base, "logo.ico")
            if os.path.exists(p):
                return p
    return None


def append_log_file(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def _detect_war3():
    d = BASE_DIR
    for _ in range(3):          # 本层、上一层、上上层都找一下（适应放在子文件夹里）
        for name in ("War3.exe", "Warcraft III.exe", "Frozen Throne.exe"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
        d = os.path.dirname(d)
    return os.path.join(os.path.dirname(BASE_DIR), "War3.exe")


def default_skills():
    # 触发键预填 Q W E R D F，其余留空；默认键(target)全部留空，由你按英雄填
    trig = ["Q", "W", "E", "R", "D", "F", "", ""]
    return [{"trigger": trig[i], "target": ""} for i in range(8)]


def default_items():
    tg = ["NUMPAD7", "NUMPAD8", "NUMPAD4", "NUMPAD5", "NUMPAD1", "NUMPAD2"]
    return [{"trigger": str(i + 1), "target": tg[i]} for i in range(6)]


def default_hero():
    return {"trigger": "CAPSLOCK", "target": "F1"}


def new_profile_data():
    # 一个方案 = 技能栏 + 物品栏 + 选英雄 一整套
    return {"skills": default_skills(), "items": default_items(), "hero": default_hero()}


DEFAULT_PROFILE = "默认"


def new_config():
    return {
        "window_class": "Warcraft III",
        "war3_path": _detect_war3(),
        "windowed": False,
        "block_win": True,
        "show_hpbar": True,
        "active_profile": DEFAULT_PROFILE,
        "profiles": {DEFAULT_PROFILE: new_profile_data()},
    }


def _migrate_profiles(cfg):
    """把老配置里的全局 items/hero 并入每个方案，并补齐缺失字段。"""
    old_items = cfg.pop("items", None)     # 老版本：全局物品栏
    old_hero = cfg.pop("hero", None)       # 老版本：全局选英雄
    for prof in cfg.get("profiles", {}).values():
        if not isinstance(prof, dict):
            continue
        prof.setdefault("skills", default_skills())
        if "items" not in prof:
            prof["items"] = old_items if old_items else default_items()
        if "hero" not in prof:
            prof["hero"] = old_hero if old_hero else default_hero()


def load_config():
    # 优先读 exe 旁边用户自己保存的 config.json；没有就读打包进 exe 的默认配置。
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else (_bundled_config_path() or CONFIG_PATH)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            base = new_config()
            for k, v in base.items():
                cfg.setdefault(k, v)
            if not cfg.get("profiles"):
                cfg["profiles"] = {DEFAULT_PROFILE: new_profile_data()}
            _migrate_profiles(cfg)
            if cfg.get("active_profile") not in cfg["profiles"]:
                cfg["active_profile"] = next(iter(cfg["profiles"]))
            return cfg
        except Exception:
            pass
    return new_config()


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ====================================================================
# 引擎（键盘钩子，独立线程）
# ====================================================================
class Engine:
    def __init__(self, log_queue):
        self.q = log_queue
        self.cfg = load_config()
        self.paused = False
        self.thread_id = None
        self._hook = None
        self._proc = None
        self.win_class = "Warcraft III"
        self.remap = {}        # trigger_vk -> target_vk
        self.block_win = True  # 禁用 Win 键（防止误触最小化游戏）
        self.last_fire = {}
        self.debug = False     # 调试：把钩子收到的按键记进日志
        self.chat_mode = False # 聊天中：暂停转键，方便打字
        self._send_q = queue.Queue()   # 发键放到独立线程做，避免阻塞钩子
        self.apply(self.cfg)

    def apply(self, cfg):
        self.cfg = cfg
        self.win_class = cfg.get("window_class", "Warcraft III") or "Warcraft III"
        self.block_win = bool(cfg.get("block_win", True))
        m = {}
        # 当前方案：技能栏 + 物品栏 + 选英雄 都属于这个方案
        prof = cfg.get("profiles", {}).get(cfg.get("active_profile"), {})
        for s in prof.get("skills", []):
            tv, gv = name_to_vk(s.get("trigger")), name_to_vk(s.get("target"))
            if tv is not None and gv is not None:
                m[tv] = gv
        for it in prof.get("items", []):
            tv, gv = name_to_vk(it.get("trigger")), name_to_vk(it.get("target"))
            if tv is not None and gv is not None:
                m[tv] = gv
        h = prof.get("hero", {})
        tv, gv = name_to_vk(h.get("trigger")), name_to_vk(h.get("target"))
        if tv is not None and gv is not None:
            m[tv] = gv
        self.remap = m

    def log(self, msg):
        try:
            self.q.put(msg)
        except Exception:
            pass
        try:
            print(msg)
        except Exception:
            pass
        append_log_file(msg)

    def _fg_info(self):
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ("", "")
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, c, 256)
        t = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, t, 256)
        return (c.value, t.value)

    def is_war3_front(self):
        cls, title = self._fg_info()
        if not cls and not title:
            return False
        return cls == self.win_class or title.startswith("Warcraft III")

    def _send_worker(self):
        while True:
            vk = self._send_q.get()
            if vk is None:
                break
            try:
                self._do_send(vk)
            except Exception as e:
                self.log("发送异常: %s" % e)

    def _send_scan(self, scan, ext, up):
        flags = KEYEVENTF_SCANCODE | ext | (KEYEVENTF_KEYUP if up else 0)
        inp = INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, 0)))
        n = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if self.debug and n != 1:
            self.log("!! SendInput 失败 返回%d 错误码%d" % (n, ctypes.get_last_error()))

    def _do_send(self, vk):
        # 用“扫描码”注入，模拟真实硬件按键，DirectInput 游戏(War3)才收得到
        scan = user32.MapVirtualKeyW(vk, 0) & 0xFF
        ext = KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED_VKS else 0
        self._send_scan(scan, ext, False)   # 按下
        time.sleep(0.02)                     # 按住一小会，让游戏采样到
        self._send_scan(scan, ext, True)     # 抬起

    def send_vk(self, vk):
        self._send_q.put(vk)

    def debounced(self, vk, gap=0.03):
        now = time.time()
        if now - self.last_fire.get(vk, 0) < gap:
            return True
        self.last_fire[vk] = now
        return False

    def handle(self, vk, is_down):
        if vk == VK_PAUSE:
            if is_down:
                self.paused = not self.paused
                self.log("【已暂停】按 Pause 恢复" if self.paused else "【已恢复】改键开启")
                winsound.Beep(400 if self.paused else 900, 160)
                self.q.put("__PAUSE__" if self.paused else "__RESUME__")
            return True
        if self.paused:
            return False
        # 禁用 Win 键（游戏里按 Win 不再最小化）
        if self.block_win and vk in (0x5B, 0x5C):
            return True
        # 聊天检测：回车开/关聊天框；聊天中一律放行，方便打字(如 -apneng)、Esc 取消
        if is_down and vk == 0x0D:                       # Enter
            self.chat_mode = not self.chat_mode
            self.log("【聊天】开始打字，暂停转键" if self.chat_mode else "【聊天】结束，恢复转键")
            self.q.put("__CHAT_ON__" if self.chat_mode else "__CHAT_OFF__")
            return False
        if is_down and vk == 0x1B and self.chat_mode:    # Esc 取消聊天
            self.chat_mode = False
            self.log("【聊天】取消，恢复转键")
            self.q.put("__CHAT_OFF__")
            return False
        if self.chat_mode:
            return False
        target = self.remap.get(vk)
        if target is not None:
            if is_down and not self.debounced(vk):
                self.send_vk(target)
            return True   # 吞掉原键（按下+抬起都吞）
        return False

    def low_level_proc(self, nCode, wParam, lParam):
        try:
            if nCode == 0:
                kb = ctypes.cast(lParam, LPKBDLLHOOKSTRUCT).contents
                injected = bool(kb.flags & LLKHF_INJECTED)
                is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                is_up = wParam in (WM_KEYUP, WM_SYSKEYUP)
                front = self.is_war3_front()
                if self.debug and is_down and not injected:
                    vk = kb.vkCode
                    ch = chr(vk) if 0x30 <= vk <= 0x5A else ""
                    tgt = self.remap.get(vk)
                    extra = ""
                    if not front:
                        c, t = self._fg_info()
                        extra = "  [当前前台 类名=%r 标题=%r]" % (c, t)
                    self.log("按键 %s(0x%02X)  魔兽前台=%s  命中转键=%s%s%s" % (
                        ch, vk, "是" if front else "否",
                        "是" if tgt is not None else "否",
                        ("→发送0x%02X" % tgt) if tgt is not None else "", extra))
                if front and not injected and (is_down or is_up):
                    if self.handle(kb.vkCode, is_down):
                        return 1
        except Exception as e:
            try:
                self.log("钩子异常: %s" % e)
            except Exception:
                pass
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def run(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        threading.Thread(target=self._send_worker, daemon=True).start()
        self._proc = HOOKPROC(self.low_level_proc)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc,
                                              kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            self.log("安装键盘钩子失败(错误码 %d)，请用【启动改键.bat】以管理员运行。"
                     % ctypes.get_last_error())
            self.q.put("__HOOK_FAIL__")
            return
        self.log("引擎已启动，改键生效中（只在魔兽窗口里）。")
        self.q.put("__HOOK_OK__")
        adm = is_elevated()
        if adm:
            self.log("本程序管理员权限：是 ✓")
            self.q.put("__ADMIN_YES__")
        else:
            self.log("本程序管理员权限：否 —— 这张图的魔兽是管理员运行，本程序也必须管理员，"
                     "否则改键全部无效！请关掉本程序，用 DotA改键精灵.exe 启动并在UAC点“是”。")
            self.q.put("__ADMIN_NO__")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def stop(self):
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)


# ====================================================================
# 图形界面
# ====================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DotA 改键精灵")
        self.resizable(False, False)
        # 设置窗口图标(标题栏+任务栏)：在窗口真正显示(map)之后再设，
        # 否则会被 Tk 映射时的默认图标覆盖，所以延迟并在 <Map> 时再执行一次。
        self.after(150, self._apply_window_icon)
        self.bind("<Map>", lambda e: self._apply_window_icon(), add="+")
        try:
            open(LOG_PATH, "w", encoding="utf-8").close()   # 每次启动清空旧日志
        except Exception:
            pass
        self.q = queue.Queue()
        self.engine = Engine(self.q)
        self.active = self.engine.cfg.get("active_profile", "默认")

        self.skill_trig = []   # 8 个触发键 var
        self.skill_targ = []   # 8 个默认键 var
        self.item_trig = []    # 6 个物品触发键 var
        self._build_ui()
        self._load_globals(self.engine.cfg)
        self._reload_profiles_combo()
        self._load_profile_to_ui(self.active)

        self.engine_thread = threading.Thread(target=self.engine.run, daemon=True)
        self.engine_thread.start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(80, self._poll_queue)

    # ---------- 窗口图标 ----------
    def _apply_window_icon(self):
        """标题栏 + 任务栏都用 logo.ico 作为图标。"""
        try:
            p = icon_path()
            if p:
                self.iconbitmap(default=p)   # default: 之后弹出的对话框也一并生效
        except Exception:
            pass

    # ---------- 键位框：点一下框、按一下想用的键就自动填 ----------
    def _mk_key_entry(self, parent, var, width):
        e = ttk.Entry(parent, textvariable=var, width=width, justify="center")

        def on_key(event):
            if event.keysym in ("Tab", "ISO_Left_Tab"):
                return  # 让 Tab 正常切换焦点
            if event.keysym in ("BackSpace", "Delete"):
                var.set("")
                return "break"
            name = vk_to_name(event.keycode)
            if not name and event.char and event.char.isprintable() and event.char != " ":
                name = event.char.upper()
            if name:
                var.set(name)
            return "break"

        e.bind("<KeyPress>", on_key)
        return e

    # ---------- UI ----------
    def _build_ui(self):
        # 顶部状态
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(top, text="运行状态：").pack(side="left")
        self.status_var = tk.StringVar(value="启动中…")
        self.status_lbl = ttk.Label(top, textvariable=self.status_var, foreground="#c00")
        self.status_lbl.pack(side="left")
        self.chat_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.chat_var, foreground="#08c").pack(side="left", padx=6)
        self.admin_var = tk.StringVar(value="")
        self.admin_lbl = ttk.Label(top, textvariable=self.admin_var, foreground="#c00")
        self.admin_lbl.pack(side="left", padx=12)
        ttk.Button(top, text="暂停/恢复(Pause)", command=self.toggle_pause).pack(side="right")
        self.debug_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="调试(记录按键)", variable=self.debug_var,
                        command=self._toggle_debug).pack(side="right", padx=6)
        self.blockwin_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="禁用Win键", variable=self.blockwin_var,
                        command=lambda: setattr(self.engine, "block_win", self.blockwin_var.get())
                        ).pack(side="right", padx=6)

        # 魔兽启动
        wf = ttk.LabelFrame(self, text="魔兽启动")
        wf.pack(fill="x", padx=10, pady=5)
        r1 = ttk.Frame(wf); r1.pack(fill="x", padx=6, pady=4)
        ttk.Label(r1, text="War3.exe：").pack(side="left")
        self.war3_path_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.war3_path_var, width=40).pack(side="left", padx=3)
        ttk.Button(r1, text="浏览…", command=self.browse_war3).pack(side="left")
        self.windowed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(r1, text="窗口模式", variable=self.windowed_var).pack(side="left", padx=6)
        self.hpbar_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(r1, text="显示血条", variable=self.hpbar_var,
                        command=self._toggle_hpbar).pack(side="left", padx=6)
        ttk.Button(r1, text="▶ 启动魔兽", command=self.launch_war3).pack(side="left")

        # 方案
        pf = ttk.LabelFrame(self, text="方案（不同英雄默认键不同）")
        pf.pack(fill="x", padx=10, pady=5)
        pr = ttk.Frame(pf); pr.pack(fill="x", padx=6, pady=4)
        ttk.Label(pr, text="当前方案：").pack(side="left")
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(pr, textvariable=self.profile_var,
                                          state="readonly", width=16)
        self.profile_combo.pack(side="left", padx=3)
        self.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_switch)
        ttk.Button(pr, text="新建", width=6, command=self.new_profile).pack(side="left", padx=2)
        ttk.Button(pr, text="重命名", width=6, command=self.rename_profile).pack(side="left", padx=2)
        ttk.Button(pr, text="删除", width=6, command=self.delete_profile).pack(side="left", padx=2)

        # 技能栏
        sk = ttk.LabelFrame(self, text="技能栏（该技能默认键 → 自定义键）")
        sk.pack(fill="x", padx=10, pady=5)
        for i in range(8):
            # 按列排：技能1-4 竖排在左列，技能5-8 竖排在右列
            col = 0 if i < 4 else 4
            row = 2 + (i % 4)
            fr = ttk.Frame(sk)
            fr.grid(row=row, column=col, columnspan=4, sticky="w", padx=6, pady=2)
            ttk.Label(fr, text="技能%d" % (i + 1), width=5).pack(side="left")
            gv = tk.StringVar()                                       # 默认键(左)
            self._mk_key_entry(fr, gv, 7).pack(side="left", padx=2)
            ttk.Label(fr, text="→").pack(side="left")
            tv = tk.StringVar()                                       # 自定义键(右)
            self._mk_key_entry(fr, tv, 7).pack(side="left", padx=2)
            self.skill_trig.append(tv)
            self.skill_targ.append(gv)

        # 物品栏 + 选英雄
        bt = ttk.Frame(self); bt.pack(fill="x", padx=10, pady=0)
        it = ttk.LabelFrame(bt, text="物品栏（小键盘默认键 → 自定义键）")
        it.pack(side="left", fill="both", expand=True, padx=(0, 4))
        labels = ["格1", "格2", "格3", "格4", "格5", "格6"]
        sends = ["Num7", "Num8", "Num4", "Num5", "Num1", "Num2"]
        for i in range(6):
            fr = ttk.Frame(it); fr.grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=2)
            ttk.Label(fr, text="%s %-5s" % (labels[i], sends[i]), foreground="#333").pack(side="left")
            ttk.Label(fr, text="→").pack(side="left")
            v = tk.StringVar()
            self._mk_key_entry(fr, v, 6).pack(side="left", padx=2)
            self.item_trig.append(v)

        hero = ttk.LabelFrame(bt, text="选英雄（默认键 → 自定义键）")
        hero.pack(side="left", fill="both", padx=(4, 0))
        hr = ttk.Frame(hero); hr.pack(padx=6, pady=6)
        ttk.Label(hr, text="默认").pack(side="left")
        self.hero_targ_var = tk.StringVar()
        self._mk_key_entry(hr, self.hero_targ_var, 7).pack(side="left", padx=2)
        ttk.Label(hr, text="→ 自定义").pack(side="left")
        self.hero_trig_var = tk.StringVar()
        self._mk_key_entry(hr, self.hero_trig_var, 9).pack(side="left", padx=2)

        # 底部
        bottom = ttk.Frame(self); bottom.pack(fill="x", padx=10, pady=6)
        ttk.Button(bottom, text="保存并应用", command=self.save_apply).pack(side="left")
        ttk.Button(bottom, text="重置", command=self.reset_current).pack(side="left", padx=6)

        # 日志框：默认隐藏，勾“调试(记录按键)”才显示
        self.logf = ttk.LabelFrame(self, text="日志")
        logf = self.logf
        bar = ttk.Frame(logf); bar.pack(fill="x", padx=4, pady=(2, 0))
        ttk.Button(bar, text="复制日志", command=self.copy_log).pack(side="left")
        ttk.Button(bar, text="清空", command=self.clear_log).pack(side="left", padx=4)
        ttk.Label(bar, text="(日志也会自动存到程序旁边的 log.txt)",
                  foreground="#888").pack(side="left", padx=6)
        self.log_text = tk.Text(logf, height=5, width=70, state="disabled",
                                font=("Consolas", 9), wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

    # ---------- 载入 / 收集 ----------
    def _load_globals(self, cfg):
        # 只放全局设置(魔兽路径/窗口/血条等)；技能栏、物品栏、选英雄跟着方案走
        self.war3_path_var.set(cfg.get("war3_path", ""))
        self.windowed_var.set(bool(cfg.get("windowed", False)))
        self.blockwin_var.set(bool(cfg.get("block_win", True)))
        self.hpbar_var.set(bool(cfg.get("show_hpbar", True)))

    def _reload_profiles_combo(self):
        names = list(self.engine.cfg.get("profiles", {}).keys())
        self.profile_combo["values"] = names
        if self.active in names:
            self.profile_var.set(self.active)
        elif names:
            self.active = names[0]
            self.profile_var.set(self.active)

    def _load_profile_to_ui(self, name):
        prof = self.engine.cfg.get("profiles", {}).get(name, {})
        skills = prof.get("skills", default_skills())
        for i in range(8):
            s = skills[i] if i < len(skills) else {"trigger": "", "target": ""}
            self.skill_trig[i].set(s.get("trigger", ""))
            self.skill_targ[i].set(s.get("target", ""))
        items = prof.get("items", default_items())
        for i in range(6):
            self.item_trig[i].set(items[i].get("trigger", "") if i < len(items) else "")
        hero = prof.get("hero", default_hero())
        self.hero_trig_var.set(hero.get("trigger", ""))
        self.hero_targ_var.set(hero.get("target", ""))

    def _store_ui_to_profile(self, name):
        skills = []
        for i in range(8):
            skills.append({"trigger": self.skill_trig[i].get().strip().upper(),
                           "target": self.skill_targ[i].get().strip().upper()})
        tg = ["NUMPAD7", "NUMPAD8", "NUMPAD4", "NUMPAD5", "NUMPAD1", "NUMPAD2"]
        items = [{"trigger": self.item_trig[i].get().strip().upper(), "target": tg[i]}
                 for i in range(6)]
        hero = {"trigger": self.hero_trig_var.get().strip().upper(),
                "target": self.hero_targ_var.get().strip().upper()}
        self.engine.cfg.setdefault("profiles", {})[name] = {
            "skills": skills, "items": items, "hero": hero}

    def _collect_globals(self):
        # 只收集全局设置；技能/物品/选英雄由 _store_ui_to_profile 存进当前方案
        self.engine.cfg["war3_path"] = self.war3_path_var.get().strip()
        self.engine.cfg["windowed"] = bool(self.windowed_var.get())
        self.engine.cfg["block_win"] = bool(self.blockwin_var.get())
        self.engine.cfg["show_hpbar"] = bool(self.hpbar_var.get())

    def _validate(self):
        """检查所有非空键名是否可识别。返回错误信息或 None。"""
        def chk(v, where):
            if v and name_to_vk(v) is None:
                return "%s 无法识别的键：%r" % (where, v)
            return None
        for i in range(8):
            e = chk(self.skill_trig[i].get().strip(), "技能%d 触发键" % (i + 1)) or \
                chk(self.skill_targ[i].get().strip(), "技能%d 默认键" % (i + 1))
            if e:
                return e
        for i in range(6):
            e = chk(self.item_trig[i].get().strip(), "物品格%d" % (i + 1))
            if e:
                return e
        return chk(self.hero_trig_var.get().strip(), "选英雄触发键") or \
            chk(self.hero_targ_var.get().strip(), "选英雄发送键")

    # ---------- 方案按钮 ----------
    def on_profile_switch(self, event=None):
        new = self.profile_var.get()
        if new == self.active:
            return
        self._store_ui_to_profile(self.active)   # 先把当前编辑存进内存
        self.active = new
        self._load_profile_to_ui(new)
        self.log("已切换到方案：%s（记得点“保存并应用”）" % new)

    def new_profile(self):
        name = simpledialog.askstring("新建方案", "给这个英雄的方案起个名字：", parent=self)
        if not name:
            return
        name = name.strip()
        if not name or name in self.engine.cfg.get("profiles", {}):
            messagebox.showwarning("提示", "名字为空或已存在。")
            return
        self._store_ui_to_profile(self.active)
        self.engine.cfg["profiles"][name] = new_profile_data()
        self.active = name
        self._reload_profiles_combo()
        self._load_profile_to_ui(name)
        self.log("已新建方案：%s" % name)

    def rename_profile(self):
        old = self.active
        name = simpledialog.askstring("重命名方案", "新名字：", initialvalue=old, parent=self)
        if not name:
            return
        name = name.strip()
        profs = self.engine.cfg["profiles"]
        if not name or (name in profs and name != old):
            messagebox.showwarning("提示", "名字为空或已存在。")
            return
        self._store_ui_to_profile(old)
        profs[name] = profs.pop(old)
        self.active = name
        self._reload_profiles_combo()
        self.log("方案已重命名为：%s" % name)

    def delete_profile(self):
        if self.active == DEFAULT_PROFILE:
            messagebox.showinfo("提示", "默认方案不能删除。")
            return
        profs = self.engine.cfg["profiles"]
        if len(profs) <= 1:
            messagebox.showinfo("提示", "至少保留一个方案。")
            return
        if not messagebox.askyesno("删除方案", "确定删除方案「%s」？" % self.active):
            return
        profs.pop(self.active, None)
        self.active = next(iter(profs))
        self._reload_profiles_combo()
        self._load_profile_to_ui(self.active)
        self.log("已删除方案，当前：%s" % self.active)

    def reset_current(self):
        """清空当前方案的技能栏 / 物品栏 / 选英雄（只清界面，需再点“保存并应用”生效）。"""
        if not messagebox.askyesno(
                "重置", "确定清空当前方案「%s」的技能栏 / 物品栏 / 选英雄设置？" % self.active):
            return
        for v in self.skill_trig:
            v.set("")
        for v in self.skill_targ:
            v.set("")
        for v in self.item_trig:
            v.set("")
        self.hero_trig_var.set("")
        self.hero_targ_var.set("")
        self.log("已清空当前方案设置（记得点“保存并应用”）。")

    # ---------- 魔兽启动 ----------
    def _toggle_hpbar(self):
        set_healthbars(self.hpbar_var.get())
        self.log("显示血条：%s —— 需【重开魔兽】才生效(先关魔兽再从本工具启动最稳)。"
                 % ("开" if self.hpbar_var.get() else "关"))

    def browse_war3(self):
        init = os.path.dirname(self.war3_path_var.get()) or os.path.dirname(BASE_DIR)
        p = filedialog.askopenfilename(title="选择 War3.exe", initialdir=init,
                                       filetypes=[("魔兽主程序", "*.exe"), ("所有文件", "*.*")])
        if p:
            self.war3_path_var.set(os.path.normpath(p))

    def launch_war3(self):
        path = self.war3_path_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("找不到魔兽", "War3.exe 路径无效，请点“浏览…”选择。")
            return
        set_healthbars(self.hpbar_var.get())   # 启动前把常显血条设置好
        args = [path] + (["-window"] if self.windowed_var.get() else [])
        try:
            subprocess.Popen(args, cwd=os.path.dirname(path))
            self.log("已启动魔兽：%s" % " ".join(args))
            self.engine.cfg["war3_path"] = path
            self.engine.cfg["windowed"] = bool(self.windowed_var.get())
            save_config(self.engine.cfg)
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    # ---------- 保存 ----------
    def save_apply(self):
        err = self._validate()
        if err:
            messagebox.showerror("配置有误", err)
            return
        self._store_ui_to_profile(self.active)
        self._collect_globals()
        self.engine.cfg["active_profile"] = self.active
        save_config(self.engine.cfg)
        self.engine.apply(self.engine.cfg)
        n = len(self.engine.remap)
        self.log("已保存并应用（当前生效 %d 个转键）。" % n)

    def _toggle_debug(self):
        self.engine.debug = self.debug_var.get()
        if self.engine.debug:
            self.logf.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self.log("调试已开启：进游戏按 Q/1/CapsLock，看下面日志。")
        else:
            self.logf.pack_forget()

    def toggle_pause(self):
        self.engine.paused = not self.engine.paused
        if self.engine.paused:
            self.status_var.set("已暂停"); self.status_lbl.configure(foreground="#c80")
        else:
            self.status_var.set("运行中"); self.status_lbl.configure(foreground="#060")

    # ---------- 轮询 ----------
    def _poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg == "__HOOK_OK__":
                    self.status_var.set("运行中"); self.status_lbl.configure(foreground="#060")
                elif msg == "__HOOK_FAIL__":
                    self.status_var.set("钩子安装失败(需管理员)"); self.status_lbl.configure(foreground="#c00")
                elif msg == "__ADMIN_YES__":
                    self.admin_var.set("管理员:是"); self.admin_lbl.configure(foreground="#060")
                elif msg == "__ADMIN_NO__":
                    self.admin_var.set("管理员:否 → 改键会失效!请用exe启动"); self.admin_lbl.configure(foreground="#c00")
                elif msg == "__CHAT_ON__":
                    self.chat_var.set("（聊天中·转键暂停）")
                elif msg == "__CHAT_OFF__":
                    self.chat_var.set("")
                elif msg == "__PAUSE__":
                    self.status_var.set("已暂停"); self.status_lbl.configure(foreground="#c80")
                elif msg == "__RESUME__":
                    self.status_var.set("运行中"); self.status_lbl.configure(foreground="#060")
                else:
                    self.log(msg)
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def copy_log(self):
        txt = self.log_text.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.update()  # 确保剪贴板写入
        messagebox.showinfo("已复制", "日志已复制到剪贴板，可以粘贴发出去了。")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        try:
            open(LOG_PATH, "w", encoding="utf-8").close()
        except Exception:
            pass

    def on_close(self):
        try:
            self.engine.stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
