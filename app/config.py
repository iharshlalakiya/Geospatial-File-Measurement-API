import os


class Settings(object):
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_dir = base_dir
        self.upload_dir = os.path.join(base_dir, "storage", "uploads")
        self.database_url = os.environ.get(
            "DATABASE_URL", "sqlite:///" + os.path.join(base_dir, "app.db")
        )
        self.max_upload_size_mb = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "50"))

    def ensure_upload_dir(self):
        if not os.path.isdir(self.upload_dir):
            os.makedirs(self.upload_dir)


settings = Settings()
