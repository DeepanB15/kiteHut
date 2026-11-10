"""Phase 9.5 integration tests — end-to-end verification."""
import pytest, tempfile
from pathlib import Path
from app.agent.state.agent_state import AgentTask
from app.agent.loop94 import AgentLoop94
from app.agent.router.tool_router_contracts import get_registered_tool_names

def test_rag_exists():
    from app.rag.pipeline import RagPipeline
    assert RagPipeline is not None

def test_agent_investigate_path():
    tmp = tempfile.mkdtemp()
    (Path(tmp)/"auth.py").write_text("def auth(): pass\n")
    state = AgentLoop94(max_steps=2).run(
        AgentTask(task_id="t", query="auth", task_type="INVESTIGATE", repository_path=tmp),
        repository_path=tmp)
    assert state is not None

def test_23_registry():
    assert len(get_registered_tool_names()) == 23

def test_no_mutation(tmp=tempfile.mkdtemp()):
    p = Path(tmp); (p/"a.py").write_text("x\n")
    before = (p/"a.py").read_text()
    AgentLoop94(max_steps=1).run(AgentTask(task_id="t", query="q", task_type="QUESTION", repository_path=str(p)), repository_path=str(p))
    assert (p/"a.py").read_text() == before
