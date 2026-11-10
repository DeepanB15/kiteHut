import cycle: agent.permissions.policies -> agent.__init__ -> agent.runtime.core -> tools.registry -> tools.base (mitigated by lazy import in core.__init__ and TYPE_CHECKING guard in loop.py)
