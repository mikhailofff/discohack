import sys
import webbrowser
import requests
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QTcpServer, QHostAddress

# Конфигурация приложения Яндекс
CLIENT_ID = '4648a51ecff4419999228cdb14a168c4'
CLIENT_SECRET = '4648a51ecff4419999228cdb14a168c4'

class CloudAuthManager(QTcpServer):
    def __init__(self):
        super().__init__()
        self.access_token = None
        
        self.listen(QHostAddress.SpecialAddress.LocalHost, 8080)
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client:
            # Читаем данные из запроса браузера
            while client.canReadLine():
                line = client.readLine().data().decode()
                if "GET" in line:
                    try:
                        code = line.split("code=")[1].split(" ")[0]
                        self.exchange_code_for_token(code)
                        
                        response = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
                        response += "<h1>Успешно!</h1><p>Облако подключено. Можно закрыть вкладку.</p>"
                        client.write(response.encode())
                    except IndexError:
                        pass
            client.disconnectFromHost()

    def exchange_code_for_token(self, code):
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        }
        r = requests.post("https://oauth.yandex.ru/token", data=data)
        self.access_token = r.json().get('access_token')
        print(f"Токен получен: {self.access_token}")
        
        from PyQt6.QtWidgets import QMessageBox

        def exchange_code_for_token(self, code):
            
            if self.access_token:
                msg = QMessageBox()
                msg.setText(f"Успех! Мы получили доступ.\nТокен: {self.access_token[:10]}...")
                msg.exec()
        

class TrayApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.auth_manager = CloudAuthManager()
        
        # Настройка трея
        self.tray = QSystemTrayIcon(QIcon.fromTheme("drive-removable-media"))
        menu = QMenu()
        
        login_btn = menu.addAction("Войти в Яндекс.Диск")
        login_btn.triggered.connect(self.open_browser)
        
        menu.addSeparator()
        exit_btn = menu.addAction("Выход")
        exit_btn.triggered.connect(sys.exit)
        
        self.tray.setContextMenu(menu)
        self.tray.show()

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    tray_app = TrayApp()
    tray_app.run()