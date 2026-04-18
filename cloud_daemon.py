import os
import json
import shutil
import subprocess
import signal
from threading import Thread
from pydbus import SessionBus
from gi.repository import GLib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class YandexUploader:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://cloud-api.yandex.net/v1/disk/resources"
        self.headers = {"Authorization": f"OAuth {self.token}"}
        self.session = self._build_session()
        self.transfer_timeout = (3, 300)

    def _build_session(self):
        retry = Retry(total=5, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def upload_file(self, disk_path: str, local_file: str):
        if not os.path.isfile(local_file):
            raise FileNotFoundError(local_file)

        check = requests.get(
            self.base_url,
            headers=self.headers,
            params={"path": disk_path}
        )
        if check.status_code == 200:
            requests.delete(
                self.base_url,
                headers=self.headers,
                params={"path": disk_path, "permanently": "true"}
            )

        resp = requests.get(
            f"{self.base_url}/upload",
            headers=self.headers,
            params={"path": disk_path, "overwrite": "true"},
        )
        resp.raise_for_status()
        href = resp.json()["href"]

        with open(local_file, "rb") as f:
            upload_resp = self.session.put(
                href,
                data=f,
                headers={"Content-Type": "application/octet-stream"},
                timeout=self.transfer_timeout,
            )
        upload_resp.raise_for_status()
        print(f"[OK] Uploaded {local_file} -> {disk_path}")

    def get_public_url(self, disk_path: str, local_file: str):
        check = requests.get(
            self.base_url,
            headers=self.headers,
            params={"path": disk_path}
        )
        if check.status_code != 200:
            self.upload_file(disk_path, local_file)

        resp = requests.post(
            f"{self.base_url}/publish",
            headers=self.headers,
            params={"path": disk_path},
        )
        resp.raise_for_status()
        public_url = resp.json().get("public_url")
        return public_url

class CloudService(object):
    dbus = """
    <node>
      <interface name="ru.hackathon.CloudService">
        <method name="HandleAction">
          <arg type="s" name="action_type" direction="in"/>
          <arg type="s" name="file_path" direction="in"/>
        </method>
      </interface>
    </node>
    """

    def __init__(self):
        config_path = os.path.expanduser("~/.cloud_bridge_config.json")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
            token = config.get("token")
        else:
            raise RuntimeError(f"Config not found: {config_path}")

        if not token:
            raise RuntimeError("Yandex token not found in config")
        self.uploader = YandexUploader(token)

    def HandleAction(self, action_type, file_path):
        filename = os.path.basename(file_path)
        disk_path = f"/{filename}"
        notifier = shutil.which("notify-send")

        try:
            if action_type == "upload":
                if notifier:
                    subprocess.Popen([notifier, "Cloud", f"Uploading {filename}..."])
                self.uploader.upload_file(disk_path, file_path)
                if notifier:
                    subprocess.Popen([notifier, "Cloud", f"{filename} uploaded successfully!"])
                print(f"[OK] Uploaded {file_path} -> {disk_path}")

            elif action_type == "get_url":
                if notifier:
                    subprocess.Popen([notifier, "Cloud", f"Generating public URL for {filename}..."])
                public_url = self.uploader.get_public_url(disk_path, file_path)
                if notifier:
                    subprocess.Popen([notifier, "Cloud", f"Public URL: {public_url}"])
                print(f"[OK] Public URL for {filename}: {public_url}")

        except Exception as e:
            print(f"[ERR] Runtime error: {e}")
            if notifier:
                subprocess.Popen([notifier, "Cloud", f"Error processing {filename}: {e}"])

def start_dbus():
    loop = GLib.MainLoop()
    try:
        bus = SessionBus()
        bus.publish("ru.hackathon.CloudService", ("/ru/hackathon/CloudService", CloudService()))
        print(">>> DBUS SERVICE PUBLISHED: /ru/hackathon/CloudService")
        loop.run()
    except Exception as e:
        print(f">>> [FATAL] DBus Error: {e}")
        os._exit(1)

def signal_handler(sig, frame):
    print("\n[INFO] SIGINT received. Stopping daemon...")
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    Thread(target=start_dbus, daemon=True).start()
    print(">>> CLOUD DAEMON RUNNING (Press Ctrl+C to exit)")
    try:
        while True:
            signal.pause()
    except KeyboardInterrupt:
        pass
