import sys
import subprocess
import os
import shutil
import signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer
from pydbus import SessionBus
from threading import Thread
from gi.repository import GLib

class CloudService(object):
    """
    DBus Service interface definition
    """
    dbus = """
    <node>
      <interface name="ru.hackathon.CloudService">
        <method name="HandleAction">
          <arg type="s" name="action_type" direction="in"/>
          <arg type="s" name="file_path" direction="in"/>
        </method>
      </interface>
    </node>
    """

    def HandleAction(self, action_type, file_path):
        print(f"\n[OK] Action received: {action_type} for {file_path}")

        filename = os.path.basename(file_path)
        notifier = shutil.which("notify-send")

        try:
            if action_type == "upload":
                if notifier:
                    subprocess.Popen([notifier, 'Cloud', f'Uploading {filename}...'])
                print(f"--- Uploading: {filename} ---")

            elif action_type == "get_url":
                if notifier:
                    subprocess.Popen([notifier, 'Cloud', f'Generating link for {filename}...'])
                print(f"--- Generating URL for: {filename} ---")

        except Exception as e:
            print(f"[ERR] Runtime error: {e}")

def start_dbus():
    loop = GLib.MainLoop()
    try:
        bus = SessionBus()
        bus.publish("ru.hackathon.CloudService", ("/ru/hackathon/CloudService", CloudService()))
        print(">>> DBUS SERVICE PUBLISHED: /ru/hackathon/CloudService")
        loop.run()
    except Exception as e:
        print(f">>> [FATAL] DBus Error: {e}")
        os._exit(1)

def signal_handler(sig, frame):
    print("\n[INFO] SIGINT received. Stopping daemon...")
    app.quit()

# Initialize Application
app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

# Setup Signal Handling for Ctrl+C
signal.signal(signal.SIGINT, signal_handler)

# Keep Python interpreter awake to catch signals
timer = QTimer()
timer.start(500)
timer.timeout.connect(lambda: None)

# System Tray Setup
tray = QSystemTrayIcon(QIcon.fromTheme("folder-cloud"))
menu = QMenu()
status_item = menu.addAction("Status: Connected")
status_item.setEnabled(False)
menu.addSeparator()

exit_btn = menu.addAction("Exit")
exit_btn.triggered.connect(app.quit)

tray.setContextMenu(menu)
tray.show()

# Start DBus Thread
Thread(target=start_dbus, daemon=True).start()

print(">>> CLOUD DAEMON RUNNING (Press Ctrl+C to exit)")
sys.exit(app.exec())
