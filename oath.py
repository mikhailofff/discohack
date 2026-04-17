import sys
import webbrowser
import requests
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QTcpServer, QHostAddress


CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080

class AuthServer(QTcpServer):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.access_token = None
        
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT):
            print(f"Не удалось запустить сервер на порту {REDIRECT_PORT}")
        
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        print("--- [DEBUG] Кто-то стучится в порт 8080! ---")
        client = self.nextPendingConnection()
        if client:
            client.waitForReadyRead(2000) 
            data = client.readAll().data().decode()
            print(f"--- [DEBUG] Получены данные:\n{data[:100]}...") 

            if "GET" in data:
                try:
                    # Ищем code=
                    parts = data.split("code=")
                    if len(parts) > 1:
                        code = parts[1].split(" ")[0]
                        print(f"--- [DEBUG] Найден код: {code}")
                        
                        response = (
                            "HTTP/1.1 200 OK\r\n"
                            "Content-Type: text/html; charset=utf-8\r\n\r\n"
                            "Успех! Ключ перехвачен."
                        )
                        client.write(response.encode())
                        self.exchange_code_for_token(code)
                except Exception as e:
                    print(f"--- [DEBUG] Ошибка разбора: {e}")
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
            result = r.json()
            self.access_token = result.get('access_token')
            if self.access_token:
                print(f"\n[УСПЕХ] Токен получен: {self.access_token}")
                self.on_success()
        except Exception as e:
            print(f"Ошибка сети: {e}")

    def on_success(self):
        msg = QMessageBox()
        msg.setWindowTitle("Яндекс.Диск")
        msg.setText("Авторизация прошла успешно!")
        msg.exec()

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.server = AuthServer()
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)
        self.menu = QMenu()
        login_action = self.menu.addAction("Войти в Диск")
        login_action.triggered.connect(self.open_browser)
        exit_action = self.menu.addAction("Выход")
        exit_action.triggered.connect(sys.exit)
        self.tray.setContextMenu(self.menu)
        self.tray.show()

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def run(self):
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())