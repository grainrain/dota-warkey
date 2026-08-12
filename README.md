# DotA 改键精灵

Warcraft III / DotA 专用的**纯键盘转键**改键工具。按下【自定义键】，程序就把【游戏默认键】发给魔兽——和物品栏、选英雄一个道理，**全屏也 100% 有效**，不用标定、不动鼠标。

纯 Python 标准库（含 tkinter），无需安装任何第三方依赖即可运行源码。

## 功能

- **技能栏**：8 个技能槽，每槽「自定义键 → 该英雄该技能的默认键」。
- **物品栏**：按 1–6 发送小键盘 Num7/8/4/5/1/2（魔兽物品栏原生热键）。
- **选英雄**：按 CapsLock → 发送 F1。
- **方案**：不同英雄默认键不同，用「方案」保存多套技能配置，随时切换。
- **聊天自动放行**：游戏里按回车打字时自动暂停转键，Esc / 再次回车恢复。
- **常显血条**：可一键改魔兽游戏选项（改注册表，重开魔兽生效）。
- Pause 键随时暂停 / 恢复。

## 直接运行源码

需要 Windows + Python 3（自带 tkinter）。**必须以管理员身份运行**，否则键盘钩子收不到按键、改键无效。

```bash
python dota_warkey.py
```

（若魔兽是管理员启动的，本程序也必须管理员。）

## 打包成单文件 exe

已配置好 PyInstaller，产物是一个**单文件、内置管理员提权、带图标**的 exe，`config.json` 和 `logo.ico` 会被打进 exe（默认配置 + 窗口图标）。

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean dota_warkey.spec
```

或直接双击 `build.bat`。产物在 `dist\DotA改键精灵.exe`。

等价的一行命令：

```bash
pyinstaller --noconfirm --onefile --windowed --uac-admin --icon logo.ico --name "DotA改键精灵" --add-data "config.json;." --add-data "logo.ico;." dota_warkey.py
```

## 配置说明（config.json）

- `config.json` 是**默认配置**，会被打进 exe。exe 首次运行、且旁边没有 `config.json` 时就用这份默认值。
- 运行后在界面里改键并「保存并应用」，配置会写到 **exe 旁边**的 `config.json`（用户设置优先于内置默认）。所以分发时只给一个 exe 即可，用户自己的改动会保存在本地。

## 文件说明

| 文件 | 说明 |
|---|---|
| `dota_warkey.py` | 主程序源码 |
| `config.json` | 默认配置（打进 exe） |
| `logo.png` | 图标原图 |
| `logo.ico` | 窗口 + exe 图标（由 logo.png 生成，打进 exe） |
| `dota_warkey.spec` | PyInstaller 打包脚本 |
| `build.bat` | 一键打包 |
| `.gitignore` | 忽略打包产物等 |

## 备注

- 仅支持 Windows。
- 需要管理员权限（安装低级键盘钩子）。
- 图标 `logo.png` / `logo.ico` 为魔兽争霸相关素材（暴雪版权），仅供个人使用；如需公开分发，请自行替换为无版权图标。
