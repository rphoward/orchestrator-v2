from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Founder:
    id: int = field(default_factory=lambda: 0)
    name: Optional[str] = None
    startup_name: Optional[str] = None
    vision: Optional[str] = None

@dataclass
class Message:
    role: str  # 'founder', 'consultant', 'system'
    content: str
    metadata: Dict = field(default_factory=dict)

@dataclass
class ArchitecturalSpec:
    id: int = field(default_factory=lambda: 0)
    domains: Dict[str, str] = field(default_factory=dict)
    core_ethos: Optional[str] = None

    def update_domain(self, domain_name: str, synthesis: str):
        self.domains[domain_name] = synthesis

@dataclass
class InterviewSession:
    id: int = field(default_factory=lambda: 0)
    founder: Founder = field(default_factory=Founder)
    messages: List[Message] = field(default_factory=list)
    spec: ArchitecturalSpec = field(default_factory=ArchitecturalSpec)
    status: str = "active" # active, completed
    context_index: Dict[str, any] = field(default_factory=dict) # Pseudo-RAG Memory Indexing structure

    def add_message(self, role: str, content: str, metadata: dict = None):
        msg = Message(role=role, content=content, metadata=metadata or {})
        self.messages.append(msg)
        # In a real implementation, we'd trigger the Memory (Context Compiler) to index this message here

    def complete_session(self):
        self.status = "completed"
