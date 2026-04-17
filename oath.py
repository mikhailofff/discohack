import sys
import webbrowser
import requests
import os
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QTcpServer, QHostAddress

# --- НАСТРОЙКИ ---
CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080
TOKEN_FILE = os.path.expanduser("~/.alt_drive_token")

class AuthServer(QTcpServer):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT):
            print(f"ОШИБКА: Порт {REDIRECT_PORT} занят. Введите: killall -9 python3")
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client:
            client.waitForReadyRead(2000)
            data = client.readAll().data().decode()
            
            
            if "favicon.ico" in data:
                client.disconnectFromHost()
                return

            if "GET" in data:
                try:
                    
                    current_code = data.split("code=")[1].split(" ")[0]
                    
                    
                    if hasattr(self, 'last_processed_code') and self.last_processed_code == current_code:
                        client.disconnectFromHost()
                        return
                    
                    self.last_processed_code = current_code 

                    
                    response = (
                        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                        "Connection: close\r\n\r\n"
                        "<html><body><h2>Авторизация успешна!</h2><p>Окно можно закрыть.</p></body></html>"
                    )
                    client.write(response.encode())
                    client.flush()
                    
                    
                    self.exchange_code_for_token(current_code)
                    
                except (IndexError, Exception):
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
                QMessageBox.information(None, "Успех", "Авторизация прошла успешно!")
            else:
                print(f"Ошибка Яндекса: {res}")
        except Exception as e:
            print(f"Ошибка сети: {e}")

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.server = AuthServer()
        
        # Проверка токена при старте
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r") as f:
                saved_token = f.read().strip()
                print(f"Получен ключ: {saved_token}")
        else:
            print("Ключ не найден. Нужно войти в аккаунт.")

        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)
        
        self.menu = QMenu()
        login_act = self.menu.addAction("Войти в Диск")
        login_act.triggered.connect(self.open_browser)
        
        logout_act = self.menu.addAction("Сбросить авторизацию")
        logout_act.triggered.connect(self.logout)
        
        self.menu.addSeparator()
        exit_act = self.menu.addAction("Выход")
        exit_act.triggered.connect(sys.exit)
        
        self.tray.setContextMenu(self.menu)
        self.tray.show()

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def logout(self):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            print("Авторизация сброшена.")
            QMessageBox.information(None, "Инфо", "Авторизация удалена.")

    def run(self):
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())