import sys

# window_helper is a thin Win32 wrapper (ctypes.windll.* + PIL.ImageGrab).
# Bail out cleanly on macOS / Linux so the captcha_server's try/except
# ImportError can set capture_browser_window = None without raising
# AttributeError halfway through import.
if sys.platform != "win32":
    raise ImportError(
        "window_helper is Windows-only. On macOS / Linux use the "
        "/captcha_direct endpoint with a base64 image from the "
        "Tampermonkey userscript."
    )

import ctypes
from ctypes import wintypes
import time
from PIL import ImageGrab

# Windows API 定义
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# Make Win32 window rectangles use the same physical-pixel coordinate space as
# PIL.ImageGrab. Without this, Chrome rects can be DPI-virtualized and crops drift.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

# 定义类型
HWND = wintypes.HWND
LPARAM = wintypes.LPARAM
LRESULT = wintypes.LPARAM
BOOL = wintypes.BOOL
DWORD = wintypes.DWORD

# 回调函数类型
WNDENUMPROC = ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM)

# API 函数声明
user32.EnumWindows.argtypes = [WNDENUMPROC, LPARAM]
user32.GetWindowTextLengthW.argtypes = [HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [HWND]
user32.SetForegroundWindow.restype = BOOL
user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
user32.ShowWindow.restype = BOOL
user32.IsWindowVisible.argtypes = [HWND]
user32.IsWindowVisible.restype = BOOL
user32.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
user32.OpenInputDesktop.argtypes = [DWORD, BOOL, DWORD]
user32.OpenInputDesktop.restype = wintypes.HANDLE
user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
user32.SetThreadDesktop.restype = BOOL
user32.IsIconic.argtypes = [HWND]
user32.IsIconic.restype = BOOL
user32.GetForegroundWindow.restype = HWND

SW_RESTORE = 9
SW_SHOW = 5
DESKTOP_READOBJECTS = 0x0001
DESKTOP_ENUMERATE = 0x0040
DESKTOP_WRITEOBJECTS = 0x0080
DESKTOP_SWITCHDESKTOP = 0x0100
_INPUT_DESKTOP = None


def ensure_input_desktop():
    """Attach this thread to the interactive desktop before window/capture APIs."""
    global _INPUT_DESKTOP
    access = (
        DESKTOP_READOBJECTS
        | DESKTOP_ENUMERATE
        | DESKTOP_WRITEOBJECTS
        | DESKTOP_SWITCHDESKTOP
    )
    hdesk = user32.OpenInputDesktop(0, False, access)
    if not hdesk:
        return False
    _INPUT_DESKTOP = hdesk
    return bool(user32.SetThreadDesktop(hdesk))

def get_window_title(hwnd):
    """获取窗口标题"""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value

def get_window_rect(hwnd):
    """获取窗口位置"""
    rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None

def find_windows(keywords):
    """
    查找包含关键词的窗口
    keywords: 关键词列表，如 ['Chrome', 'Edge', 'Firefox', 'bigmodel']
    """
    ensure_input_desktop()
    windows = []
    
    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            title = get_window_title(hwnd)
            if any(keyword.lower() in title.lower() for keyword in keywords):
                rect = get_window_rect(hwnd)
                windows.append({
                    'hwnd': hwnd,
                    'title': title,
                    'rect': rect
                })
        return True
    
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return windows

def bring_to_front(hwnd):
    """将窗口置于顶层，同时避免改变最大化状态"""
    ensure_input_desktop()
    
    # 如果已经是前台窗口，直接返回，省掉几百毫秒
    if user32.GetForegroundWindow() == hwnd:
        return True
        
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.05) # 压缩延迟
        else:
            user32.ShowWindow(hwnd, SW_SHOW)
            
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.05) # 压缩延迟
        return True
    except Exception as e:
        print(f"窗口置顶失败: {e}")
        return False

def _rect_distance(rect, preferred_rect):
    if not rect or not preferred_rect:
        return None
    left, top, right, bottom = rect
    px = float(preferred_rect.get('x', preferred_rect.get('left', 0)))
    py = float(preferred_rect.get('y', preferred_rect.get('top', 0)))
    pw = float(preferred_rect.get('width', 0))
    ph = float(preferred_rect.get('height', 0))
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    pcx = px + pw / 2
    pcy = py + ph / 2
    size_penalty = abs((right - left) - pw) * 0.25 + abs((bottom - top) - ph) * 0.25
    return abs(cx - pcx) + abs(cy - pcy) + size_penalty

def capture_browser_window(browser_keywords=None, preferred_title=None, preferred_rect=None):
    """
    查找浏览器窗口并截图
    返回: (PIL.Image, window_rect)
    """
    if browser_keywords is None:
        browser_keywords = [
            'Chrome', 'Edge', 'Firefox', 'Brave', 'Opera', 
            'bigmodel', '智谱', 'GLM'
        ]
    
    ensure_input_desktop()
    print("正在查找浏览器窗口...")
    windows = find_windows(browser_keywords)
    
    if not windows:
        print("未找到浏览器窗口")
        return None, None
    
    # 选择第一个找到的窗口
    window = windows[0]
    if preferred_rect:
        scored = []
        for candidate in windows:
            score = _rect_distance(candidate.get('rect'), preferred_rect)
            if score is not None:
                scored.append((score, candidate))
        if scored:
            scored.sort(key=lambda item: item[0])
            window = scored[0][1]
    elif preferred_title:
        preferred = preferred_title.lower()
        for candidate in windows:
            title = candidate.get('title', '')
            if preferred in title.lower() or title.lower() in preferred:
                window = candidate
                break
    print(f"找到窗口: {window['title']}")
    
    # 置顶窗口 (如果需要)
    bring_to_front(window['hwnd'])

    # 极大压缩等待时间，或者在已经是前台时完全不等待
    if user32.GetForegroundWindow() != window['hwnd']:
        time.sleep(0.1)
    
    window['rect'] = get_window_rect(window['hwnd'])

    # 截图
    if window['rect']:
        left, top, right, bottom = window['rect']
        screen = ImageGrab.grab(bbox=(left, top, right, bottom))
        print(f"已截取窗口: {right-left}x{bottom-top}")
        return screen, window['rect']
    else:
        # 回退到全屏截图
        screen = ImageGrab.grab()
        print("无法获取窗口位置，使用全屏截图")
        return screen, None

def list_all_windows():
    """列出所有可见窗口（用于调试）"""
    ensure_input_desktop()
    windows = []
    
    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            title = get_window_title(hwnd)
            if title:
                windows.append(title)
        return True
    
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return windows

if __name__ == "__main__":
    print("="*60)
    print("窗口调试工具")
    print("="*60)
    
    print("\n所有可见窗口:")
    all_windows = list_all_windows()
    for i, title in enumerate(all_windows, 1):
        try:
            print(f"  {i}. {title}")
        except:
            pass
    
    print("\n查找浏览器窗口...")
    img, rect = capture_browser_window()
    
    if img:
        print(f"\n截图成功，尺寸: {img.size}")
        img.save("browser_capture.png")
        img.show()
        print("已保存为 browser_capture.png")
    else:
        print("\n截图失败")
