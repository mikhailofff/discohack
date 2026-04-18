import sys
import webbrowser
import requests
import os
import json
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QStyle, 
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFileDialog # Добавлен QFileDialog
)
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QTcpServer, QHostAddress

# --- НАСТРОЙКИ ---
CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080
# Файл сохранится в папке пользователя. Можно заменить на "token.txt" для локального хранения.
TOKEN_FILE = os.path.expanduser("~/.alt_drive_config.json")

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
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(token)
                
                print("-" * 40)
                print(f"[УСПЕХ] Новый токен получен и сохранен: {token}")
                print(f"[ФАЙЛ] Путь: {TOKEN_FILE}")
                print("-" * 40)
                
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
        
        self.config_file = os.path.expanduser("~/.alt_drive_config.json")
        
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
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.path_input.setText(data.get("cache_path", ""))
                    self.limit_input.setText(str(data.get("limit_size", "")))
            except Exception as e:
                print(f"Ошибка загрузки настроек: {e}")

    def save_settings(self):
        data = {
            "cache_path": self.path_input.text(),
            "limit_size": self.limit_input.text()
        }
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"[КОНФИГ] Настройки сохранены в {self.config_file}")
            self.accept()
        except Exception as e:
            print(f"Ошибка сохранения: {e}")

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        
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
        
        # Сборка меню
        self.menu.addAction(self.login_act)
        self.menu.addAction(self.logout_act)
        self.menu.addAction(self.settings_act)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_act)
        
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        
        # Первичная проверка при запуске
        self.refresh_ui()

    def refresh_ui(self):
        """Проверяет токен и настраивает видимость кнопок"""
        has_token = os.path.exists(TOKEN_FILE)
        
        if has_token:
            try:
                with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                    token = f.read().strip()
                
                if token:
                    self.login_act.setVisible(False)
                    self.logout_act.setVisible(True)
                    print(f"[СТАТУС] Авторизован. Токен: {token[:15]}...")
                    return
            except:
                pass
        
        # Если файла нет или он пустой
        self.login_act.setVisible(True)
        self.logout_act.setVisible(False)
        print("[СТАТУС] Требуется вход.")

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def logout(self):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            print("[!] Авторизация удалена пользователем.")
            self.refresh_ui()
            self.tray.showMessage("Яндекс.Диск", "Сессия сброшена.", QSystemTrayIcon.MessageIcon.Information)

    def run(self):
        return self.qt_app.exec()
    
    def open_settings(self):
        self.dialog = SettingsDialog()
        self.dialog.show()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())
