from services.user import UserService

def test_create_user():
    svc = UserService()
    result = svc.create_user({"id": 1, "name": "Alice"})
    assert result["name"] == "Alice"
