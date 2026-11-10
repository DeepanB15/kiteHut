"""Sample repository root module."""
from services.auth import AuthService
from services.user import UserService
from models.user import User
import os

APP_NAME = "demo"

def get_config():
    return {"env": "development"}

class App:
    """Application entrypoint."""

    def __init__(self):
        self.user_service = UserService()
        self.auth_service = AuthService()

    def run(self):
        print("App started")
