import os

from app.config import settings


def save_upload_bytes(file_id, filename, content):
    settings.ensure_upload_dir()
    file_dir = os.path.join(settings.upload_dir, file_id)
    if not os.path.isdir(file_dir):
        os.makedirs(file_dir)
    destination_path = os.path.join(file_dir, filename)
    with open(destination_path, "wb") as buffer:
        buffer.write(content)
    return destination_path
