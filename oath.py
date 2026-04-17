import sys
import webbrowser
import requests
import os
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QTcpServer, QHostAddress

# --- НАСТРОЙКИ ---
CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080
TOKEN_FILE = os.path.expanduser("~/.alt_drive_token")

class AuthServer(QTcpServer):
    def __init__(self, app_instance, parent=None):
        super().__init__(parent)
        self.app_instance = app_instance
        self.processed_codes = set()
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT):
            print(f"ОШИБКА: Порт {REDIRECT_PORT} занят.")
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client:
            client.waitForReadyRead(2000)
            raw_data = client.readAll().data().decode()
            
            # Игнорируем лишние запросы
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
                    "<html><body><h2>Успешно!</h2></body></html>"
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
        data = {'grant_type': 'authorization_code', 'code': code, 'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET}
        try:
            r = requests.post(url, data=data)
            token = r.json().get('access_token')
            if token:
                with open(TOKEN_FILE, "w") as f:
                    f.write(token)
                print(f"Получен ключ: {token}")
                # Вызываем обновление UI
                self.app_instance.refresh_ui()
                QMessageBox.information(None, "Успех", "Авторизация прошла успешно!")
        except Exception as e:
            print(f"Ошибка сети: {e}")

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.server = AuthServer(self)
        
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)
        
        # Создаем ОДНО меню на все время работы
        self.menu = QMenu()
        
        # Создаем действия (кнопки)
        self.login_act = QAction("Войти в Диск", self.menu)
        self.login_act.triggered.connect(self.open_browser)
        
        self.logout_act = QAction("Сбросить авторизацию", self.menu)
        self.logout_act.triggered.connect(self.logout)
        
        self.exit_act = QAction("Выход", self.menu)
        self.exit_act.triggered.connect(sys.exit)
        
        # Добавляем их в меню (порядок важен)
        self.menu.addAction(self.login_act)
        self.menu.addAction(self.logout_act)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_act)
        
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        
        # Первичная настройка видимости
        self.refresh_ui()

    def refresh_ui(self):
        """Прячет или показывает нужные кнопки в зависимости от наличия токена"""
        has_token = os.path.exists(TOKEN_FILE)
        
        if has_token:
            self.login_act.setVisible(False)
            self.logout_act.setVisible(True)
            try:
                with open(TOKEN_FILE, "r") as f:
                    print(f"Получен ключ: {f.read().strip()}")
            except: pass
        else:
            self.login_act.setVisible(True)
            self.logout_act.setVisible(False)
            print("Ключ не найден. Режим входа.")

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def logout(self):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            print("Авторизация сброшена.")
            self.refresh_ui()
            QMessageBox.information(None, "Инфо", "Авторизация удалена.")

    def run(self):
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())