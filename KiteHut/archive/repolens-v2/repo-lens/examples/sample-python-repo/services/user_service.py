"""User service."""
from models.user import User

class UserService:
    def __init__(self):
        self.users = {}

    def create_user(self, data):
        user = User(
            id=data.get("id"),
            name=data.get("name"),
            email=data.get("email"),
        )
        self.users[user.id] = user
        return user.to_dict()

    def get_user(self, user_id):
        return self.users.get(user_id).to_dict() if user_id in self.users else None
