import argparse
import os
import sys
import json
import webbrowser
import requests

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QStyle,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog # Добавлен QFileDialog
)
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QTcpServer, QHostAddress

from fuse import FUSE
from engine import CloudFUSE

CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080
config_file = os.path.expanduser("~/.cloud_bridge_config.json")
#os.path.expanduser("~/.cloud_bridge_config.json")


def readConfig():
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    return {}

def writeConfig(config):
    print(config_file)
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)
        return
 #   else:
 #       new_config = {
 #           'token': token,
 #           'cache': cache_dir,
#            'limit': limit_gb
#        }

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
            # Ждем данные чуть дольше для стабильности чтения
            if not client.waitForReadyRead(3000):
                client.disconnectFromHost()
                return

            raw_data = client.readAll().data().decode()

            # Строгая фильтрация: игнорируем favicon и запросы без кода
            if "GET /?code=" not in raw_data:
                client.disconnectFromHost()
                return

            try:
                # Извлекаем код (между "code=" и следующим пробелом или символом &)
                start_idx = raw_data.find("code=") + 5
                end_idx = raw_data.find(" ", start_idx)
                fragment = raw_data[start_idx:end_idx]
                code = fragment.split('&')[0].strip()

                if not code or code in self.processed_codes:
                    client.disconnectFromHost()
                    return

                self.processed_codes.add(code)
                print(f"\n[*] Пойман код авторизации: {code}")

                # Отправляем ответ в браузер
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

                # Запускаем обмен кода на токен
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
                # ЗАПИСЬ В ФАЙЛ
                config = readConfig()
                config['token'] = token
                writeConfig(config)

                print("-" * 40)
                print(f"[УСПЕХ] Новый токен получен и сохранен: {token}")
                print("-" * 40)

                #########

               # token = args.token or saved_config.get('token')
               # cache_dir = args.cache or saved_config.get('cache', "~/.cache/yandex_cloud_fuse")
               # limit_gb = args.limit or saved_config.get('limit', 1)
               # new_config = {
               #     'token': token,
               #     'cache': cache_dir,
               #    'limit': limit_gb
               # }
               # save_config(new_config)
                mountpoint = '/home/ad/cloud'
                cache_dir = config.get('cache')
                limit_bytes = limit_gb * 1024 * 1024 * 1024
                print(f"Запуск с конфигом из {config_file}")
                print(f"Токен: {token[:5]}***{token[-5:]}")
                model = CloudFUSE(token=token, cache_dir=cache_dir, max_cache_size=limit_bytes)
                FUSE(model, mountpoint, foreground=True, nothreads=True, nonempty=True)

                #########

                # Обновляем интерфейс
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

        # --- Секция выбора пути ---
        layout.addWidget(QLabel("Путь к папке кеша:"))
        path_layout = QHBoxLayout()

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Выберите папку...")

        # Кнопка с иконкой папки из стандартного стиля системы
        self.browse_btn = QPushButton()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.browse_btn.setIcon(icon)
        self.browse_btn.setToolTip("Выбрать папку в проводнике")
        self.browse_btn.clicked.connect(self.browse_folder)

        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        # --- Секция лимита ---
        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("Лимит кеша (МБ):"))
        self.limit_input = QLineEdit()
        limit_layout.addWidget(self.limit_input)
        layout.addLayout(limit_layout)

        # --- Кнопка сохранения ---
        self.save_btn = QPushButton("Сохранить параметры")
        self.save_btn.setStyleSheet("font-weight: bold; padding: 5px;")
        self.save_btn.clicked.connect(self.save_settings)
        layout.addWidget(self.save_btn)

        self.setLayout(layout)
        self.load_settings()

    def browse_folder(self):
        # Открываем диалог выбора директории
        directory = QFileDialog.getExistingDirectory(self, "Выберите папку для кеша")
        if directory:
            self.path_input.setText(directory)

    def load_settings(self):
        config = readConfig()
        self.path_input.setText(config.get("cache", ""))
        self.limit_input.setText(str(config.get("limit", "")))

    def save_settings(self):
        config = {
            "cache": self.path_input.text(),
            "limit": self.limit_input.text()
        }
        writeConfig(config)
        print(f"[КОНФИГ] Настройки сохранены в {config_file}")
        self.accept()

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        parser = argparse.ArgumentParser(description="Yandex Disk FUSE Driver")
        parser.add_argument('--mountpoint', '-m', type=str, help="Mount point directory")
        parser.add_argument('--token', '-t', type=str, help="OAuth token")
        parser.add_argument('--cache', '-c', type=str, help="Path to local cache")
        parser.add_argument('--limit', '-l', type=int, help="Cache size limit in GB")
        parser.add_argument('--config','-cf', type=str, help="Path to config file")
        args = parser.parse_args()

        global config_file
        config_file = args.config or config_file

        # Инициализация сервера
        self.server = AuthServer(self)

        # Иконка и трей
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)

        self.menu = QMenu()
        # КЛЮЧЕВОЙ МОМЕНТ: Обновлять меню ПЕРЕД его открытием
        self.menu.aboutToShow.connect(self.refresh_ui)

        self.login_act = QAction("Войти в Диск", self.menu)
        self.login_act.triggered.connect(self.open_browser)

        self.logout_act = QAction("Сбросить авторизацию", self.menu)
        self.logout_act.triggered.connect(self.logout)

        self.settings_act = QAction("Параметры кеша", self.menu)
        self.settings_act.triggered.connect(self.open_settings)

        self.exit_act = QAction("Выход", self.menu)
        self.exit_act.triggered.connect(sys.exit)

        self.launch_engine_act = QAction('Запуск FUSE engine')
        self.launch_engine_act.triggered.connect(self.launch_engine)

        self.kill_engine_act = QAction('Kill FUSE engine')
        self.kill_engine_act.triggered.connect(self.kill_engine)

        # Сборка меню
        self.menu.addAction(self.login_act)
        self.menu.addAction(self.logout_act)
        self.menu.addAction(self.settings_act)
        self.menu.addAction(self.launch_engine_act)
        self.menu.addAction(self.kill_engine_act)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_act)

        self.tray.setContextMenu(self.menu)
        self.tray.show()

        # Первичная проверка при запуске
        self.refresh_ui()


    def refresh_ui(self):
        """Проверяет токен и настраивает видимость кнопок"""
        config = readConfig()
        token = config.get('token')
        print(token)
        if token:
            self.login_act.setVisible(False)
            self.logout_act.setVisible(True)
            print(f"[СТАТУС] Авторизован. Токен: {token[:15]}...")


           # mountpoint = '/home/ad/cloud'
           # cache_dir = config.get('cache')
           # limit_bytes = config.get('limit') * 1024 * 1024 * 1024
           # print(f"Запуск с конфигом из {config_file}")
           # print(f"Токен: {token[:5]}***{token[-5:]}")
           # model = CloudFUSE(token=token, cache_dir=cache_dir, max_cache_size=limit_bytes)
           # FUSE(model, mountpoint, foreground=True, nothreads=True, nonempty=True)

            return

        self.login_act.setVisible(True)
        self.logout_act.setVisible(False)
        print("[СТАТУС] Требуется вход.")

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def logout(self):
        config = readConfig()
        config["token"] = ''
        print("[!] Авторизация удалена пользователем.")
        self.refresh_ui()
        self.tray.showMessage("Яндекс.Диск", "Сессия сброшена.", QSystemTrayIcon.MessageIcon.Information)

    def run(self):
        return self.qt_app.exec()

    def open_settings(self):
        self.dialog = SettingsDialog()
        self.dialog.show()


    def launch_engine(self):
        print("debug")
        config = readConfig()

        mountpoint = '/home/ad/cloud'
        token = config.get('token')
        cache_dir = config.get('cache')
        limit_bytes = config.get('limit') * 1024 * 1024 * 1024
        print(f"Запуск с конфигом из {config_file}")
        print(f"Токен: {token[:5]}***{token[-5:]}")
        model = CloudFUSE(token=token, cache_dir=cache_dir, max_cache_size=limit_bytes)
        FUSE(model, mountpoint, foreground=True, nothreads=True, nonempty=True)

    def kill_engine(self):
        print("KILL YOURSELF NOW")

if __name__ == '__main__':
    app = CloudTrayApp()
    sys.exit(app.run())
