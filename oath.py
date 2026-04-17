import sys
import webbrowser
import requests
import keyring  # Библиотека для работы с KWallet/Gnome Keyring
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QTcpServer, QHostAddress

# --- НАСТРОЙКИ ПРИЛОЖЕНИЯ ---
CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080
APP_NAME = "AltLinuxCloud" # Имя папки в кошельке KDE

class AuthServer(QTcpServer):
    def __init__(self, parent=None):
        super().__init__(parent)
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT):
            print(f"Ошибка: Не удалось занять порт {REDIRECT_PORT}")
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client:
            client.waitForReadyRead(2000)
            data = client.readAll().data().decode()
            if "GET" in data:
                try:
                    code = data.split("code=")[1].split(" ")[0]
                    response = (
                        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                        "Connection: close\r\n\r\n"
                        "<html><body style='text-align:center;padding-top:50px;font-family:sans-serif;'>"
                        "<h2>Авторизация успешна!</h2><p>Окно можно закрыть.</p></body></html>"
                    )
                    client.write(response.encode())
                    client.flush()
                    self.exchange_code_for_token(code)
                except Exception as e:
                    print(f"Ошибка при разборе кода: {e}")
            
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
            result = r.json()
            token = result.get('access_token')
            if token:
                # СОХРАНЕНИЕ В KEYRING (KWallet)
                keyring.set_password(APP_NAME, "yandex_token", token)
                print(f"Получен ключ: {token}")
                self.on_success()
            else:
                print(f"Ошибка Яндекса: {result}")
        except Exception as e:
            print(f"Ошибка сети: {e}")

    def on_success(self):
        msg = QMessageBox()
        msg.setWindowTitle("Яндекс.Диск")
        msg.setText("Авторизация прошла успешно и сохранена в системе!")
        msg.exec()

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.server = AuthServer()
        
        # ПРОВЕРКА СУЩЕСТВУЮЩЕГО ТОКЕНА ПРИ СТАРТЕ
        saved_token = keyring.get_password(APP_NAME, "yandex_token")
        if saved_token:
            print(f"Получен ключ: {saved_token}")
        else:
            print("Требуется авторизация (ключ не найден в KWallet)")

        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)
        
        self.menu = QMenu()
        login_action = self.menu.addAction("Войти в Диск")
        login_action.triggered.connect(self.open_browser)
        
        # Добавим кнопку сброса (на случай смены аккаунта)
        logout_action = self.menu.addAction("Сбросить авторизацию")
        logout_action.triggered.connect(self.logout)
        
        self.menu.addSeparator()
        exit_action = self.menu.addAction("Выход")
        exit_action.triggered.connect(sys.exit)
        
        self.tray.setContextMenu(self.menu)
        self.tray.show()

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def logout(self):
        try:
            keyring.delete_password(APP_NAME, "yandex_token")
            QMessageBox.information(None, "Яндекс.Диск", "Авторизация сброшена.")
            print("Авторизация удалена из Keyring.")
        except:
            pass

    def run(self):
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())