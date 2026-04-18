import sys
import webbrowser
import requests
import os
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QStyle
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
            
            if "code=" not in raw_data:
                client.disconnectFromHost()
                return

            try:
                # Извлекаем код авторизации
                code = raw_data.split("code=")[1].split(" ")[0]
                
                if code in self.processed_codes:
                    client.disconnectFromHost()
                    return
                
                self.processed_codes.add(code)
                
                # Отправляем ответ браузеру СРАЗУ
                response = (
                    "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                    "Connection: close\r\n\r\n"
                    "<html><body><h2>Авторизация получена! Проверьте консоль и приложение.</h2></body></html>"
                )
                client.write(response.encode())
                client.flush()
                client.waitForBytesWritten(1000)
                client.disconnectFromHost()
                
                # Теперь запрашиваем токен
                self.exchange_code_for_token(code)
            except Exception as e:
                print(f"Ошибка при обработке запроса: {e}")

    def exchange_code_for_token(self, code):
        url = "https://oauth.yandex.ru/token"
        data = {
            'grant_type': 'authorization_code', 
            'code': code, 
            'client_id': CLIENT_ID, 
            'client_secret': CLIENT_SECRET
        }
        try:
            print(f"[*] Запрос токена для кода: {code[:5]}...")
            r = requests.post(url, data=data, timeout=10)
            res_data = r.json()
            token = res_data.get('access_token')
            
            if token:
                # ЗАПИСЬ В ФАЙЛ
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(token)
                
                # ВЫВОД В КОНСОЛЬ
                print("-" * 30)
                print(f"[УСПЕХ] Токен получен: {token}")
                print(f"[ПУТЬ] Сохранено в: {TOKEN_FILE}")
                print("-" * 30)
                
                # ОБНОВЛЕНИЕ UI
                self.app_instance.refresh_ui()
                self.app_instance.tray.showMessage(
                    "Яндекс.Диск", 
                    "Авторизация успешна!", 
                    QSystemTrayIcon.MessageIcon.Information
                )
            else:
                print(f"[ОШИБКА] Сервер не вернул токен: {res_data}")
                
        except Exception as e:
            print(f"[ОШИБКА СЕТИ] Не удалось получить токен: {e}")

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        
        # Инициализируем сервер
        self.server = AuthServer(self)
        
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)
        
        self.menu = QMenu()
        # Этот сигнал заставляет меню перепроверять наличие файла КАЖДЫЙ РАЗ перед открытием
        self.menu.aboutToShow.connect(self.refresh_ui)
        
        self.login_act = QAction("Войти в Диск", self.menu)
        self.login_act.triggered.connect(self.open_browser)
        
        self.logout_act = QAction("Сбросить авторизацию", self.menu)
        self.logout_act.triggered.connect(self.logout)
        
        self.exit_act = QAction("Выход", self.menu)
        self.exit_act.triggered.connect(sys.exit)
        
        self.menu.addAction(self.login_act)
        self.menu.addAction(self.logout_act)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_act)
        
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        
        self.refresh_ui()

    def refresh_ui(self):
        has_token = os.path.exists(TOKEN_FILE)
        
        # Переключаем видимость кнопок
        self.login_act.setVisible(not has_token)
        self.logout_act.setVisible(has_token)
        
        if has_token:
            try:
                with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                    t = f.read().strip()
                    print(f"[СТАТУС] Авторизован. Текущий токен: {t[:10]}...")
            except:
                pass
        else:
            print("[СТАТУС] Ожидание входа...")

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def logout(self):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            print("[!] Авторизация сброшена пользователем.")
            self.refresh_ui()
            self.tray.showMessage("Инфо", "Сессия завершена.", QSystemTrayIcon.MessageIcon.Information)

    def run(self):
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())