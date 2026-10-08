from .assistant import Assistant
from .base import BaseAgent
from .class_clown import ClassClown
from .deep_thinker import DeepThinker
from .inquisitive_mind import InquisitiveMind
from .note_taker import NoteTaker
from .teacher import Teacher

AGENT_CLASSES = [Teacher, Assistant, ClassClown, DeepThinker, NoteTaker, InquisitiveMind]

__all__ = [
    "BaseAgent", "AGENT_CLASSES", "Teacher", "Assistant", "ClassClown",
    "DeepThinker", "NoteTaker", "InquisitiveMind",
]
