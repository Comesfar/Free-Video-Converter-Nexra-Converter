import os
import sys

def create_desktop_shortcut():
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        
        # Check both OneDrive Desktop and standard Desktop
        onedrive_desktop = os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop")
        std_desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        
        target_dir = onedrive_desktop if os.path.exists(onedrive_desktop) else std_desktop
        lnk_path = os.path.join(target_dir, "Nexra Video Compressor.lnk")
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        vbs_path = os.path.join(current_dir, "NexraConverter.vbs")
        
        shortcut = shell.CreateShortCut(lnk_path)
        shortcut.TargetPath = "wscript.exe"
        shortcut.Arguments = f'"{vbs_path}"'
        shortcut.WorkingDirectory = current_dir
        shortcut.Description = "Nexra Video Boyut Küçültücü"
        shortcut.Save()
        print(f"Masaüstü kısayolu oluşturuldu: {lnk_path}")
        return True
    except Exception as e:
        print(f"Kısayol oluşturulamadı: {e}")
        return False

if __name__ == "__main__":
    create_desktop_shortcut()
