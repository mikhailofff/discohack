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
# Файл сохранится в папке пользователя. Можно заменить на "token.txt" для локального хранения.
TOKEN_FILE = os.path.expanduser("~/.alt_drive_token")

class AuthServer(QTcpServer):
    def __init__(self, app_instance, parent=None):
        super().__init__(parent)
        self.app_instance = app_instance
        self.processed_codes = set()
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, REDIRECT_PORT):
            print(f"ОШИБКА: Порт {REDIRECT_PORT} занят. Проверьте, не запущена ли копия программы.")
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        client = self.nextPendingConnection()
        if client:
            # Ждем данные чуть дольше для стабильности чтения
            if not client.waitForReadyRead(3000):
                client.disconnectFromHost()
                return

            raw_data = client.readAll().data().decode()
            
            # Строгая фильтрация: игнорируем favicon и запросы без кода
            if "GET /?code=" not in raw_data:
                client.disconnectFromHost()
                return

            try:
                # Извлекаем код (между "code=" и следующим пробелом или символом &)
                start_idx = raw_data.find("code=") + 5
                end_idx = raw_data.find(" ", start_idx)
                fragment = raw_data[start_idx:end_idx]
                code = fragment.split('&')[0].strip()
                
                if not code or code in self.processed_codes:
                    client.disconnectFromHost()
                    return
                
                self.processed_codes.add(code)
                print(f"\n[*] Пойман код авторизации: {code}")

                # Отправляем ответ в браузер
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html; charset=utf-8\r\n"
                    "Connection: close\r\n\r\n"
                    "<html><body style='font-family:sans-serif; text-align:center; padding-top:50px;'>"
                    "<h2>Успешно!</h2><p>Вы авторизованы. Теперь это окно можно закрыть.</p>"
                    "</body></html>"
                )
                client.write(response.encode())
                client.flush()
                client.waitForBytesWritten(1000)
                client.disconnectFromHost()
                
                # Запускаем обмен кода на токен
                self.exchange_code_for_token(code)
                
            except Exception as e:
                print(f"[!] Ошибка обработки запроса: {e}")
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
            print("[*] Запрос токена у Яндекса...")
            r = requests.post(url, data=data, timeout=10)
            res_json = r.json()
            token = res_json.get('access_token')
            
            if token:
                # ЗАПИСЬ В ФАЙЛ
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(token)
                
                print("-" * 40)
                print(f"[УСПЕХ] Новый токен получен и сохранен: {token}")
                print(f"[ФАЙЛ] Путь: {TOKEN_FILE}")
                print("-" * 40)
                
                # Обновляем интерфейс
                self.app_instance.refresh_ui()
                self.app_instance.tray.showMessage(
                    "Яндекс.Диск", 
                    "Авторизация прошла успешно!", 
                    QSystemTrayIcon.MessageIcon.Information
                )
            else:
                print(f"[ОШИБКА API] Яндекс вернул ошибку: {res_json}")
                
        except Exception as e:
            print(f"[ОШИБКА СЕТИ] Не удалось связаться с сервером: {e}")

class CloudTrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        
        # Инициализация сервера
        self.server = AuthServer(self)
        
        # Иконка и трей
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.tray = QSystemTrayIcon(icon)
        
        self.menu = QMenu()
        # КЛЮЧЕВОЙ МОМЕНТ: Обновлять меню ПЕРЕД его открытием
        self.menu.aboutToShow.connect(self.refresh_ui)
        
        self.login_act = QAction("Войти в Диск", self.menu)
        self.login_act.triggered.connect(self.open_browser)
        
        self.logout_act = QAction("Сбросить авторизацию", self.menu)
        self.logout_act.triggered.connect(self.logout)
        
        self.exit_act = QAction("Выход", self.menu)
        self.exit_act.triggered.connect(sys.exit)
        
        # Сборка меню
        self.menu.addAction(self.login_act)
        self.menu.addAction(self.logout_act)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_act)
        
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        
        # Первичная проверка при запуске
        self.refresh_ui()

    def refresh_ui(self):
        """Проверяет токен и настраивает видимость кнопок"""
        has_token = os.path.exists(TOKEN_FILE)
        
        if has_token:
            try:
                with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                    token = f.read().strip()
                
                if token:
                    self.login_act.setVisible(False)
                    self.logout_act.setVisible(True)
                    print(f"[СТАТУС] Авторизован. Токен: {token[:15]}...")
                    return
            except:
                pass
        
        # Если файла нет или он пустой
        self.login_act.setVisible(True)
        self.logout_act.setVisible(False)
        print("[СТАТУС] Требуется вход.")

    def open_browser(self):
        url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={CLIENT_ID}"
        webbrowser.open(url)

    def logout(self):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            print("[!] Авторизация удалена пользователем.")
            self.refresh_ui()
            self.tray.showMessage("Яндекс.Диск", "Сессия сброшена.", QSystemTrayIcon.MessageIcon.Information)

    def run(self):
        return self.qt_app.exec()

if __name__ == "__main__":
    app = CloudTrayApp()
    sys.exit(app.run())