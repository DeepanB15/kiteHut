import requests

def test_health():
    r = requests.get("http://localhost:8000/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_repositories():
    r = requests.get("http://localhost:8000/repositories", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert data[0]["name"] == "fixture-python-repo"

def test_graph_by_uuid():
    repo_id = "b48b8199-64df-4089-8a39-ab5852778a20"
    r = requests.get(f"http://localhost:8000/graph/{repo_id}", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3  # known persisted relationships
