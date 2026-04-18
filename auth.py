import sys
import webbrowser
import requests
import os
import json
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QStyle, 
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFileDialog
)
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QTcpServer, QHostAddress

CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080
TOKEN_FILE = os.path.expanduser("~/.alt_drive_config.json")
MOUNT_POINT = os.path.expanduser("~/Cloud")

class AuthServer(QTcpServer):
    def __init__(self, app_instance, parent=None):
        super().__init__(parent)
        self.app_instance = app_instance
        self.processed_codes = set()
        self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT)
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client and client.waitForReadyRead(3000):
            raw_data = client.readAll().data().decode()
            if "GET /?code=" in raw_data:
                start_idx = raw_data.find("code=") + 5
                end_idx = raw_data.find(" ", start_idx)
                code = raw_data[start_idx:end_idx].split('&')[0].strip()
                
                response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\nSuccess! Close this tab."
                client.write(response.encode())
                client.disconnectFromHost()
                
                self.exchange_code_for_token(code)

    def exchange_code_for_token(self, code):
        url = "https://yandex.ru"
        data = {'grant_type': 'authorization_code', 'code': code, 
                'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET}
        try:
            r = requests.post(url, data=data, timeout=10)
            token = r.json().get('access_token')
            if token:
                with open(TOKEN_FILE, "w") as f:
                    f.write(token)
                self.app_instance.start_fuse_daemon(token)
                self.app_instance.refresh_ui()
        except Exception as e:
            print(f"Auth error: {e}")

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.fuse_process = None # Храним ссылку на процесс демона
        
        self.server = AuthServer(self)
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)
        
        self.menu = QMenu()
        self.login_act = QAction("Войти в Диск", self.menu)
        self.login_act.triggered.connect(self.open_browser)
        self.logout_act = QAction("Выйти (Stop FUSE)", self.menu)
        self.logout_act.triggered.connect(self.logout)
        self.exit_act = QAction("Выход", self.menu)
        self.exit_act.triggered.connect(self.terminate_all)

        self.menu.addAction(self.login_act)
        self.menu.addAction(self.logout_act)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_act)
        
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        self.refresh_ui()

    def start_fuse_daemon(self, token):
        if self.fuse_process:
            self.stop_fuse_daemon()
        
        if not os.path.exists(MOUNT_POINT):
            os.makedirs(MOUNT_POINT)

        script_path = os.path.join(os.path.dirname(__file__), "test_fuse.py")
        # Запускаем: python3 test_fuse.py /mount --token <token>
        self.fuse_process = subprocess.Popen(
            [sys.executable, script_path, MOUNT_POINT, "--token", token],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"[FUSE] Started on {MOUNT_POINT}")

    def stop_fuse_daemon(self):
        if self.fuse_process:
            self.fuse_process.terminate()
            self.fuse_process = None
            # Принудительное размонтирование для чистоты
            subprocess.run(["fusermount", "-u", MOUNT_POINT], stderr=subprocess.DEVNULL)
            print("[FUSE] Stopped")

    def refresh_ui(self):
        has_token = os.path.exists(TOKEN_FILE)
        self.login_act.setVisible(not has_token)
        self.logout_act.setVisible(has_token)
        
        if has_token and not self.fuse_process:
            with open(TOKEN_FILE, "r") as f:
                token = f.read().strip()
                if token: self.start_fuse_daemon(token)

    def open_browser(self):
        url = f"https://yandex.ru{CLIENT_ID}"
        webbrowser.open(url)

    def logout(self):
        self.stop_fuse_daemon()
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        self.refresh_ui()

    def terminate_all(self):
        self.stop_fuse_daemon()
        sys.exit()

    def run(self):
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())

