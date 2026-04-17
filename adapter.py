import logging

logger = logging.getLogger("Adapter")

def get_remote_files():
    logger.info("Fetching files from Yandex.Disk (Mock)...")
    return [
        {'name': 'document.pdf', 'size': 1024500},
        {'name': 'photo.jpg', 'size': 5400300},
        {'name': 'notes.txt', 'size': 450}
    ]

def download_file_content(path):
    return b"Real data from Yandex will be here soon!"