import sys
from fuse import FUSE
from engine import CloudFUSE


def main():
    # Папка, куда будем "вешать" диск
    # Можно передать аргументом: python test_fuse.py ./my_disk
    if len(sys.argv) < 2:
        print("Usage: python test_fuse.py <mountpoint>")
        return

    mountpoint = sys.argv[1]

    # Инициализируем твое ядро
    model = CloudFUSE()

    print(f"--- Запуск FUSE на {mountpoint} ---")
    print("Нажми Ctrl+C для остановки")

    # Запуск магии.
    # foreground=True - чтобы видеть ошибки в этой консоли
    # nothreads=True - для упрощения отладки (в один поток)
    FUSE(model, mountpoint, foreground=True, nothreads=True)


if __name__ == '__main__':
    main()