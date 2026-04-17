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
    """Сервер для автоматического приема кода авторизации"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.access_token = None
        
        if not self.listen(QHostAddress.LocalHost, REDIRECT_PORT):
            print(f"Не удалось запустить сервер на порту {REDIRECT_PORT}")
        
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client:
            while client.canReadLine():
                line = client.readLine().data().decode()
                # Ищем GET запрос, который пришлет Яндекс после клика пользователя
                if "GET" in line:
                    try:
                       
                        code = line.split("code=")[1].split(" ")[0]
                        self.exchange_code_for_token(code)
                        
                        response = (
                            "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
                            "<html><body style='font-family: sans-serif; text-align: center; margin-top: 50px;'>"
                            "<h2 style='color: #2c3e50;'>Авторизация успешна!</h2>"
                            "<p>Приложение получило ключ. Теперь вы можете закрыть эту вкладку.</p>"
                            "</body></html>"
                        )
                        client.write(response.encode())
                    except Exception as e:
                        print(f"Ошибка при разборе кода: {e}")
            client.disconnectFromHost()

    def exchange_code_for_token(self, code):
        """Обмен кода на токен через API Яндекса"""
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
            else:
                print(f"[ОШИБКА] Яндекс не выдал токен: {result}")
        except Exception as e:
            print(f"[ОШИБКА] Проблема с сетью: {e}")

    def on_success(self):
        """Действия после успешного получения ключа"""
        msg = QMessageBox()
        msg.setWindowTitle("Яндекс.Диск")
        msg.setText("Авторизация прошла успешно!\nТеперь облако будет подключено к вашей папке Home/cloud.")
        msg.exec()
        # Здесь ваша команда вставит функцию монтирования:
        # mount_folder(self.access_token)

class CloudTrayApp:
    def __init__(self):
        # Создаем приложение Qt
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False) # Чтобы приложение не закрылось без окон

        # Запускаем локальный сервер
        self.server = AuthServer()

        # Настраиваем иконку (берем стандартную "Drive" из системы)
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        
        # Создаем трей
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("Яндекс.Диск Альт Линукс")

        # Создаем меню трея
        self.menu = QMenu()
        
        login_action = self.menu.addAction("Войти и подключить Диск")
        login_action.triggered.connect(self.open_browser)
        
        self.menu.addSeparator()
        
        exit_action = self.menu.addAction("Выйти из программы")
        exit_action.triggered.connect(sys.exit)

        self.tray.setContextMenu(self.menu)
        self.tray.show()

    def open_browser(self):
        """Открывает браузер для авторизации"""
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        print(f"Открываем ссылку: {url}")
        webbrowser.open(url)

    def run(self):
        # Запуск цикла событий Qt
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())