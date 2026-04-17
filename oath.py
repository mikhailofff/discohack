import sys
import webbrowser
import requests
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QTcpServer, QHostAddress

# --- ВСТАВЬТЕ ВАШИ ДАННЫЕ ИЗ ЯНДЕКС ID ---
CLIENT_ID = 'ВАШ_ID'
CLIENT_SECRET = 'ВАШ_SECRET'
REDIRECT_PORT = 8080

class AuthServer(QTcpServer):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.access_token = None
        # ИСПРАВЛЕНО: Добавлен SpecialAddress для совместимости с PyQt6
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT):
            print(f"Не удалось запустить сервер на порту {REDIRECT_PORT}")
        
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client:
            while client.canReadLine():
                line = client.readLine().data().decode()
                if "GET" in line:
                    try:
                        code = line.split("code=")[1].split(" ")[0]
                        self.exchange_code_for_token(code)
                        response = (
                            "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
                            "<html><body style='font-family: sans-serif; text-align: center; margin-top: 50px;'>"
                            "<h2>Авторизация успешна!</h2><p>Можете закрыть вкладку.</p></body></html>"
                        )
                        client.write(response.encode())
                    except Exception as e:
                        print(f"Ошибка разбора: {e}")
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