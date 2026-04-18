import argparse
import json
import os
import shutil
import subprocess
import sys
import webbrowser

import requests
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QHostAddress, QTcpServer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
)

CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080
CONFIG_FILE = os.path.expanduser("~/.cloud_bridge_config.json")


def readConfig():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}


def writeConfig(config):
    print(CONFIG_FILE)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def parse_limit_mb(raw_limit, default_mb=1024):
    try:
        limit_mb = int(raw_limit)
        return limit_mb if limit_mb > 0 else default_mb
    except (TypeError, ValueError):
        return default_mb


def normalize_fs_path(path_value):
    if not path_value:
        return path_value
    return os.path.abspath(os.path.expanduser(path_value))


class FuseProcessManager:
    def __init__(self):
        self.fuse_process = None
        self.script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_fuse.py")

    def is_running(self):
        return self.fuse_process is not None and self.fuse_process.poll() is None

    def start(self):
        config = readConfig()
        mountpoint = normalize_fs_path(config.get('mountpoint'))
        token = config.get('token')
        cache_dir = normalize_fs_path(config.get('cache'))
        limit_mb = parse_limit_mb(config.get('limit'))

        if self.is_running():
            print(f"[FUSE] Уже запущен, pid={self.fuse_process.pid}")
            return True

        if not token:
            print("[FUSE] Не удалось запустить: отсутствует токен.")
            return False
        if not mountpoint:
            print("[FUSE] Не удалось запустить: не задан mountpoint.")
            return False
        if not cache_dir:
            print("[FUSE] Не удалось запустить: не задан путь к кешу.")
            return False

        os.makedirs(mountpoint, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)

        command = [
            sys.executable,
            self.script_path,
            mountpoint,
            "--token",
            token,
            "--cache",
            cache_dir,
            "--limit",
            str(limit_mb),
            "--config",
            CONFIG_FILE,
        ]

        print(f"[FUSE] Запуск mountpoint={mountpoint}, cache={cache_dir}, limit={limit_mb}MB")
        self.fuse_process = subprocess.Popen(command, start_new_session=True)
        print(f"[FUSE] Процесс запущен, pid={self.fuse_process.pid}")
        return True

    def stop(self):
        config = readConfig()
        mountpoint = config.get('mountpoint')
        was_running = self.is_running()

        if mountpoint:
            self._unmount(mountpoint)

        if was_running:
            self.fuse_process.terminate()
            try:
                self.fuse_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("[FUSE] Процесс не завершился после terminate, отправляю kill.")
                self.fuse_process.kill()
                self.fuse_process.wait(timeout=5)
            print("[FUSE] Процесс остановлен.")
        else:
            print("[FUSE] Активный процесс не найден.")

        self.fuse_process = None
        return True

    def restart(self):
        self.stop()
        return self.start()

    def _unmount(self, mountpoint):
        for tool in ("fusermount3", "fusermount", "umount"):
            binary = shutil.which(tool)
            if not binary:
                continue

            command = [binary, "-u", mountpoint] if "fusermount" in tool else [binary, mountpoint]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"[FUSE] Размонтировано через {tool}: {mountpoint}")
                return True

            stderr = result.stderr.strip()
            if stderr:
                print(f"[FUSE] {tool} вернул ошибку: {stderr}")

        return False


class AuthServer(QTcpServer):
    def __init__(self, app_instance, parent=None):
        super().__init__(parent)
        self.app_instance = app_instance
        self.processed_codes = set()
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT):
            print(f"ОШИБКА: Порт {REDIRECT_PORT} занят. Проверьте, не запущена ли копия программы.")
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client:
            if not client.waitForReadyRead(3000):
                client.disconnectFromHost()
                return

            raw_data = client.readAll().data().decode()

            if "GET /?code=" not in raw_data:
                client.disconnectFromHost()
                return

            try:
                start_idx = raw_data.find("code=") + 5
                end_idx = raw_data.find(" ", start_idx)
                fragment = raw_data[start_idx:end_idx]
                code = fragment.split('&')[0].strip()

                if not code or code in self.processed_codes:
                    client.disconnectFromHost()
                    return

                self.processed_codes.add(code)
                print(f"\n[*] Пойман код авторизации: {code}")

                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html; charset=utf-8\r\n"
                    "Connection: close\r\n\r\n"
                    "<html><body style='font-family:sans-serif; text-align:center; padding-top:50px;'>"
                    "<h2>Успешно!</h2>"
                    "<p>Вы авторизованы. Это окно закроется через <span id='timer'>5</span>...</p>"
                    "<script>"
                    "  let seconds = 5;"
                    "  const timerElement = document.getElementById('timer');"
                    "  const interval = setInterval(() => {"
                    "    seconds--;"
                    "    timerElement.innerText = seconds;"
                    "    if (seconds <= 0) {"
                    "      clearInterval(interval);"
                    "      window.close();"
                    "    }"
                    "  }, 1000);"
                    "</script>"
                    "</body></html>"
                )
                client.write(response.encode())
                client.flush()
                client.waitForBytesWritten(1000)
                client.disconnectFromHost()

                self.exchange_code_for_token(code)

            except Exception as e:
                print(f"[!] Ошибка обработки запроса: {e}")
                client.disconnectFromHost()

    def exchange_code_for_token(self, code):
        url = "https://oauth.yandex.ru/token"
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        }
        try:
            print("[*] Запрос токена у Яндекса...")
            r = requests.post(url, data=data, timeout=10)
            res_json = r.json()
            token = res_json.get('access_token')

            if token:
                config = readConfig()
                config['token'] = token
                writeConfig(config)

                print("-" * 40)
                print(f"[УСПЕХ] Новый токен получен и сохранен: {token}")
                print("-" * 40)

                self.app_instance.fuse_manager.restart()

                self.app_instance.refresh_ui()
                self.app_instance.tray.showMessage(
                    "Яндекс.Диск",
                    "Авторизация прошла успешно!",
                    QSystemTrayIcon.MessageIcon.Information
                )
            else:
                print(f"[ОШИБКА API] Яндекс вернул ошибку: {res_json}")

        except Exception as e:
            print(f"[ОШИБКА СЕТИ] Не удалось связаться с сервером: {e}")


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки хранилища")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("mountpoint:"))
        mountpoint_layout = QHBoxLayout()

        self.mountpoint_input = QLineEdit()
        self.mountpoint_input.setPlaceholderText("Выберите папку...")

        self.select_mountpoint_btn = QPushButton()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.select_mountpoint_btn.setIcon(icon)
        self.select_mountpoint_btn.setToolTip("Выбрать папку в проводнике")
        self.select_mountpoint_btn.clicked.connect(self.browse_mountpoint)

        mountpoint_layout.addWidget(self.mountpoint_input)
        mountpoint_layout.addWidget(self.select_mountpoint_btn)
        layout.addLayout(mountpoint_layout)

        layout.addWidget(QLabel("Путь к папке кеша:"))
        path_layout = QHBoxLayout()

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Выберите папку...")

        self.browse_btn = QPushButton()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.browse_btn.setIcon(icon)
        self.browse_btn.setToolTip("Выбрать папку в проводнике")
        self.browse_btn.clicked.connect(self.browse_folder)

        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("Лимит кеша (МБ):"))
        self.limit_input = QLineEdit()
        limit_layout.addWidget(self.limit_input)
        layout.addLayout(limit_layout)

        self.save_btn = QPushButton("Сохранить параметры")
        self.save_btn.setStyleSheet("font-weight: bold; padding: 5px;")
        self.save_btn.clicked.connect(self.save_settings)
        layout.addWidget(self.save_btn)

        self.setLayout(layout)
        self.load_settings()

    def browse_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Выберите папку для кеша")
        if directory:
            self.path_input.setText(directory)

    def browse_mountpoint(self):
        directory = QFileDialog.getExistingDirectory(self, "Выберите папку для cloud")
        if directory:
            self.mountpoint_input.setText(directory)

    def load_settings(self):
        config = readConfig()
        self.path_input.setText(config.get("cache", ""))
        self.limit_input.setText(str(config.get("limit", "")))
        self.mountpoint_input.setText(str(config.get("mountpoint", "")))

    def save_settings(self):
        config = readConfig()
        config.update({
            "mountpoint": normalize_fs_path(self.mountpoint_input.text()),
            "cache": normalize_fs_path(self.path_input.text()),
            "limit": parse_limit_mb(self.limit_input.text())
        })
        writeConfig(config)
        print(f"[КОНФИГ] Настройки сохранены в {CONFIG_FILE}")
        self.accept()


class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.fuse_manager = FuseProcessManager()

        parser = argparse.ArgumentParser(description="Yandex Disk FUSE Driver")
        parser.add_argument('--mountpoint', '-m', type=str, help="Mount point directory")
        parser.add_argument('--token', '-t', type=str, help="OAuth token")
        parser.add_argument('--cache', '-c', type=str, help="Path to local cache")
        parser.add_argument('--limit', '-l', type=int, help="Cache size limit in MB")
        parser.add_argument('--config', '-cf', type=str, help="Path to config file")
        args = parser.parse_args()

        global CONFIG_FILE
        CONFIG_FILE = args.config or CONFIG_FILE

        config = readConfig()
        config_updated = {
            "mountpoint": normalize_fs_path(args.mountpoint or config.get('mountpoint')),
            "cache": normalize_fs_path(args.cache or config.get('cache')),
            "limit": parse_limit_mb(args.limit or config.get('limit')),
            "token": args.token or config.get('token', ''),
        }
        writeConfig(config_updated)

        self.server = AuthServer(self)

        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)

        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.refresh_ui)

        self.login_act = QAction("Войти в Диск", self.menu)
        self.login_act.triggered.connect(self.open_browser)

        self.toggle_sync_act = QAction("Запустить синхронизацию", self.menu)
        self.toggle_sync_act.triggered.connect(self.toggle_sync)

        self.logout_act = QAction("Сбросить авторизацию", self.menu)
        self.logout_act.triggered.connect(self.logout)

        self.settings_act = QAction("Параметры кеша", self.menu)
        self.settings_act.triggered.connect(self.open_settings)

        self.exit_act = QAction("Выход", self.menu)
        self.exit_act.triggered.connect(self.exit_app)

        self.menu.addAction(self.login_act)
        self.menu.addAction(self.toggle_sync_act)
        self.menu.addAction(self.logout_act)
        self.menu.addAction(self.settings_act)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_act)

        self.tray.setContextMenu(self.menu)
        self.tray.show()

        if self.refresh_ui():
            print('ready')
            self.fuse_manager.start()

    def refresh_ui(self):
        config = readConfig()
        token = config.get('token')
        is_running = self.fuse_manager.is_running()

        if token:
            self.login_act.setVisible(False)
            self.logout_act.setVisible(True)
            self.toggle_sync_act.setVisible(True)
            self.toggle_sync_act.setText("Остановить синхронизацию" if is_running else "Запустить синхронизацию")
            print(f"[СТАТУС] Авторизован. Токен: {token[:15]}...")
            print(f"[СТАТУС] FUSE {'запущен' if is_running else 'остановлен'}.")
            return True

        self.login_act.setVisible(True)
        self.logout_act.setVisible(False)
        self.toggle_sync_act.setVisible(False)
        print("[СТАТУС] Требуется вход.")
        return False

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def toggle_sync(self):
        if self.fuse_manager.is_running():
            self.fuse_manager.stop()
            self.tray.showMessage(
                "Яндекс.Диск",
                "Синхронизация остановлена.",
                QSystemTrayIcon.MessageIcon.Information
            )
        else:
            started = self.fuse_manager.start()
            if started:
                self.tray.showMessage(
                    "Яндекс.Диск",
                    "Синхронизация запущена.",
                    QSystemTrayIcon.MessageIcon.Information
                )
        self.refresh_ui()

    def logout(self):
        self.fuse_manager.stop()
        config = readConfig()
        config["token"] = ''
        writeConfig(config)
        print("[!] Авторизация удалена пользователем.")
        self.refresh_ui()
        self.tray.showMessage("Яндекс.Диск", "Сессия сброшена.", QSystemTrayIcon.MessageIcon.Information)

    def exit_app(self):
        self.fuse_manager.stop()
        self.qt_app.quit()

    def run(self):
        return self.qt_app.exec()

    def open_settings(self):
        self.dialog = SettingsDialog()
        self.dialog.show()


if __name__ == '__main__':
    app = CloudTrayApp()
    sys.exit(app.run())
