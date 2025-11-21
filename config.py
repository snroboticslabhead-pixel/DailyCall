import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key")
    
    # MySQL configuration for PythonAnywhere
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'DailyCall.mysql.pythonanywhere-services.com'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'DailyCall'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or 'Krishna@532'
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'DailyCall$default'

    # Simple single admin user (you can later store in DB)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


config = {
    "default": Config
}
