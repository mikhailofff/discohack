import sys
import webbrowser
import requests
import os
import keyring
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QTcpServer, QHostAddress

# --- НАСТРОЙКА СТАБИЛЬНОСТИ KEYRING ---
try:
    # Пытаемся проверить, доступен ли системный кошелек
    keyring.get_password("test", "test")
except Exception:
    # Если системный кошелек (KWallet/D-Bus) выдает ошибку,
    # принудительно используем простой зашифрованный файл
    from keyring.backends.file import EncryptedKeyring
    keyring.set_keyring(EncryptedKeyring())
    print("Системный кошелек недоступен. Используется зашифрованный файл хранилища.")

# --- ДАННЫЕ ПРИЛОЖЕНИЯ ---
CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '249440f3331c493083ad045e1f92f814'
REDIRECT_PORT = 8080
APP_NAME = "AltLinuxCloud"

class AuthServer(QTcpServer):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Исправлено для PyQt6: используем SpecialAddress
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT):
            print(f"Ошибка: Порт {REDIRECT_PORT} занят. Попробуйте 'killall -9 python3'")
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
                    print(f"Ошибка разбора кода: {e}")
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
                keyring.set_password(APP_NAME, "yandex_token", token)
                print(f"Получен ключ: {token}")
                self.on_success()
            else:
                print(f"Яндекс вернул ошибку: {result}")
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
        
        # Проверка токена при старте
        try:
            saved_token = keyring.get_password(APP_NAME, "yandex_token")
            if saved_token:
                print(f"Получен ключ: {saved_token}")
            else:
                print("Ключ не найден. Требуется вход.")
        except Exception as e:
            print(f"Ошибка чтения ключа: {e}")

        # Иконка из стандартной темы Qt
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)
        
        self.menu = QMenu()
        login_action = self.menu.addAction("Войти в Диск")
        login_action.triggered.connect(self.open_browser)
        
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
            QMessageBox.information(None, "Успех", "Авторизация сброшена.")
        except Exception as e:
            print(f"Не удалось удалить ключ: {e}")

    def run(self):
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())