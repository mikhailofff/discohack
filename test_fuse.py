import argparse
import os
import sys
import json
from fuse import FUSE
from engine import CloudFUSE

CONFIG_PATH = os.path.expanduser("~/.cloud_bridge_config.json")


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)


def main():
    saved_config = load_config()

    parser = argparse.ArgumentParser(description="Yandex Disk FUSE Driver")
    parser.add_argument('mountpoint', type=str, help="Mount point directory")
    parser.add_argument('--token', '-t', type=str, help="OAuth token")
    parser.add_argument('--cache', '-c', type=str, help="Path to local cache")
    parser.add_argument('--limit', '-l', type=int, help="Cache size limit in GB")
    args = parser.parse_args()
    token = args.token or saved_config.get('token')
    cache_dir = args.cache or saved_config.get('cache', "~/.cache/yandex_cloud_fuse")
    limit_gb = args.limit or saved_config.get('limit', 1)

    if not token:
        print("Ошибка: Токен не найден. Укажите его через --token при первом запуске.")
        sys.exit(1)
    new_config = {
        'token': token,
        'cache': cache_dir,
        'limit': limit_gb
    }
    save_config(new_config)
    mountpoint = os.path.abspath(args.mountpoint)
    cache_dir = os.path.expanduser(cache_dir)
    limit_bytes = limit_gb * 1024 * 1024 * 1024
    print(f"Запуск с конфигом из {CONFIG_PATH}")
    print(f"Токен: {token[:5]}***{token[-5:]}")
    model = CloudFUSE(token=token, cache_dir=cache_dir, max_cache_size=limit_bytes)
    FUSE(
        model,
        mountpoint,
        foreground=True,
        nothreads=False,
        max_read=131072,
        auto_cache=True,
        big_writes=True,
        nonempty=True
    )


if __name__ == '__main__':
    main()