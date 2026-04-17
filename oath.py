import sys
import webbrowser
import requests
import os
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtNetwork import QTcpServer, QHostAddress

# --- НАСТРОЙКИ ---
CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080
TOKEN_FILE = os.path.expanduser("~/.alt_drive_token")

class AuthServer(QTcpServer):
    def __init__(self, app_instance, parent=None):
        super().__init__(parent)
        self.app_instance = app_instance # Ссылка на приложение для обновления меню
        self.processed_codes = set()
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT):
            print(f"ОШИБКА: Порт {REDIRECT_PORT} занят.")
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client:
            client.waitForReadyRead(2000)
            raw_data = client.readAll().data().decode()
            
            if "favicon.ico" in raw_data or "code=" not in raw_data:
                client.disconnectFromHost()
                return

            try:
                code = raw_data.split("code=")[1].split(" ")[0]
                if code in self.processed_codes:
                    client.disconnectFromHost()
                    return
                
                self.processed_codes.add(code)
                
                response = (
                    "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                    "Connection: close\r\n\r\n"
                    "<html><body><h2>Авторизация успешна!</h2><p>Окно можно закрыть.</p></body></html>"
                )
                client.write(response.encode())
                client.flush()
                self.exchange_code_for_token(code)
            except Exception:
                pass
            
            client.waitForBytesWritten(1000)
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
            r = requests.post(url, data=data)
            res = r.json()
            token = res.get('access_token')
            if token:
                with open(TOKEN_FILE, "w") as f:
                    f.write(token)
                print(f"Получен ключ: {token}")
                # ОБНОВЛЯЕМ МЕНЮ ПОСЛЕ УСПЕХА
                self.app_instance.update_menu()
                QMessageBox.information(None, "Успех", "Авторизация прошла успешно!")
            else:
                print(f"Ошибка Яндекса: {res}")
        except Exception as e:
            print(f"Ошибка сети: {e}")

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.server = AuthServer(self)
        
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)
        
        # Создаем переменную для хранения меню, чтобы потом его удалять
        self.main_menu = None 
        
        self.update_menu()
        self.tray.show()

    def update_menu(self):
        # 1. Если меню уже существует — принудительно удаляем его из памяти
        if self.main_menu:
            self.main_menu.clear()
            self.main_menu.deleteLater() 
        
        # 2. Создаем абсолютно новый объект меню
        self.main_menu = QMenu()
        has_token = os.path.exists(TOKEN_FILE)

        if not has_token:
            print("Обновление меню: Режим входа")
            login_act = self.main_menu.addAction("Войти в Диск")
            login_act.triggered.connect(self.open_browser)
        else:
            print("Обновление меню: Режим сброса")
            logout_act = self.main_menu.addAction("Сбросить авторизацию")
            logout_act.triggered.connect(self.logout)
            
            # Читаем токен для консоли
            try:
                with open(TOKEN_FILE, "r") as f:
                    print(f"Получен ключ: {f.read().strip()}")
            except:
                pass

        self.main_menu.addSeparator()
        exit_act = self.main_menu.addAction("Выход")
        exit_act.triggered.connect(sys.exit)
        
        # 3. Устанавливаем свежее меню в трей
        self.tray.setContextMenu(self.main_menu)

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def logout(self):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            print("Авторизация сброшена.")
            self.update_menu() # Сразу обновляем меню, чтобы появилась кнопка "Войти"
            QMessageBox.information(None, "Инфо", "Авторизация удалена.")

    def run(self):
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())