"""
Nexra Video Converter & Compressor - Windows Context Menu Manager
Allows registering right-click context menu in Windows Explorer for video files.
"""

import sys
import os
import winreg

REG_BASE = r"Software\Classes\SystemFileAssociations\video\shell\NexraCompressor"


def get_default_exe_path() -> str:
    """Finds the path to Nexra Video Compressor.exe or main script."""
    # Check Desktop exe
    onedrive_desktop = os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop", "Nexra Video Compressor.exe")
    if os.path.isfile(onedrive_desktop):
        return onedrive_desktop

    std_desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "Nexra Video Compressor.exe")
    if os.path.isfile(std_desktop):
        return std_desktop

    # Check dist folder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dist_exe = os.path.join(current_dir, "dist", "Nexra Video Compressor.exe")
    if os.path.isfile(dist_exe):
        return dist_exe

    # If running inside compiled exe
    if getattr(sys, "frozen", False):
        return sys.executable

    # Fallback to pythonw.exe + main.py
    main_py = os.path.join(current_dir, "main.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.isfile(pythonw):
        return f'"{pythonw}" "{main_py}"'
    return f'python "{main_py}"'


def is_installed() -> bool:
    """Checks if Nexra context menu is installed in HKCU."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_BASE, 0, winreg.KEY_READ)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def install(exe_path: str = None) -> bool:
    """Registers Nexra cascading context menu for all video files in Windows."""
    if not exe_path:
        exe_path = get_default_exe_path()

    clean_target = exe_path if exe_path.endswith('.exe"') or exe_path.endswith(".exe") else f'"{exe_path}"'
    if not clean_target.startswith('"'):
        clean_target = f'"{clean_target}"'

    # Icon path
    icon_path = exe_path.strip('"')
    if not icon_path.endswith(".exe"):
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")

    try:
        # Root key
        root = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_BASE)
        winreg.SetValueEx(root, "MUIVerb", 0, winreg.REG_SZ, "Nexra Video Compressor")
        winreg.SetValueEx(root, "Icon", 0, winreg.REG_SZ, icon_path)
        winreg.SetValueEx(root, "SubCommands", 0, winreg.REG_SZ, "")
        winreg.CloseKey(root)

        # Submenu container
        shell = winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{REG_BASE}\\shell")

        menus = [
            ("01_open", "🎬 Nexra ile Aç & Özelleştir", f"{clean_target} \"%1\""),
            ("02_discord25", "⚡ Discord Nitro / E-posta (25 MB)", f"{clean_target} \"%1\" --target 25.0"),
            ("03_whatsapp16", "⚡ WhatsApp Hızlı Paylaşım (16 MB)", f"{clean_target} \"%1\" --target 16.0"),
            ("04_discord8", "⚡ Discord Ücretsiz / Klasik (8 MB)", f"{clean_target} \"%1\" --target 8.0"),
            ("05_telegram50", "⚡ Telegram / Standart (50 MB)", f"{clean_target} \"%1\" --target 50.0"),
        ]

        for sub_id, title, cmd_str in menus:
            sub = winreg.CreateKey(shell, sub_id)
            winreg.SetValueEx(sub, "MUIVerb", 0, winreg.REG_SZ, title)
            winreg.SetValueEx(sub, "Icon", 0, winreg.REG_SZ, icon_path)
            cmd_key = winreg.CreateKey(sub, "command")
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_str)
            winreg.CloseKey(cmd_key)
            winreg.CloseKey(sub)

        winreg.CloseKey(shell)
        return True
    except Exception as e:
        print(f"Context menu install error: {e}")
        return False


def _delete_key_tree(key, subkey):
    """Recursively deletes a Windows registry subkey."""
    try:
        open_key = winreg.OpenKey(key, subkey, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return
    while True:
        try:
            sub = winreg.EnumKey(open_key, 0)
            _delete_key_tree(open_key, sub)
        except OSError:
            break
    winreg.CloseKey(open_key)
    winreg.DeleteKey(key, subkey)


def uninstall() -> bool:
    """Removes Nexra context menu from HKCU."""
    try:
        _delete_key_tree(winreg.HKEY_CURRENT_USER, REG_BASE)
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        print(f"Context menu uninstall error: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        if uninstall():
            print("Sağ tık menüsü başarıyla kaldırıldı.")
        else:
            print("Kaldırma sırasında hata oluştu.")
    else:
        if install():
            print("Sağ tık menüsü başarıyla yüklendi!")
        else:
            print("Yükleme sırasında hata oluştu.")
