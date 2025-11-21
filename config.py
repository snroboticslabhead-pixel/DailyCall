import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key")
    MONGO_URI = os.environ.get(
        "MONGO_URI",
        "mongodb://localhost:27017/attendance_db"
    )

    # Simple single admin user (you can later store in DB)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


config = {
    "default": Config
}
