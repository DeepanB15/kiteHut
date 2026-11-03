"""Auth service."""
from models.user import User

class AuthService:
    def __init__(self):
        self.tokens = {}

    def authenticate(self, username, password):
        if username == "admin" and password == "secret":
            return {"token": "abc123"}
        return None

    def validate_token(self, token):
        return token in self.tokens
