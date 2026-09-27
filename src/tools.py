"""Drawing tools registry (extensible without touching ``main.py``)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional


class Tool(str, Enum):
    """Available drawing tools."""

    PENCIL = "pencil"
    BRUSH = "brush"
    LINE = "line"
    CIRCLE = "circle"
    RECTANGLE = "rectangle"
    TRIANGLE = "triangle"
    ERASER = "eraser"
    SELECT = "select"


@dataclass(frozen=True)
class ToolInfo:
    """Metadata for one tool (toolbar label + keyboard shortcut)."""

    tool: Tool
    label: str
    shortcut: str
    draws_shape: bool = False


_TOOL_REGISTRY: Dict[Tool, ToolInfo] = {}


def register_tool(info: ToolInfo) -> None:
    """Register (or override) a tool. Future tools plug in here."""
    _TOOL_REGISTRY[info.tool] = info


def get_tool_info(tool: Tool) -> Optional[ToolInfo]:
    """Return metadata for ``tool``, or None if unknown."""
    return _TOOL_REGISTRY.get(tool)


def available_tools() -> List[ToolInfo]:
    """All registered tools in toolbar order."""
    order = [Tool.PENCIL, Tool.BRUSH, Tool.LINE, Tool.CIRCLE,
             Tool.RECTANGLE, Tool.TRIANGLE, Tool.ERASER, Tool.SELECT]
    return [info for t in order if (info := _TOOL_REGISTRY.get(t)) is not None]


def tool_from_shortcut(key: str) -> Optional[Tool]:
    """Map a keyboard character to a tool, or None."""
    key = key.lower()
    for info in _TOOL_REGISTRY.values():
        if info.shortcut.lower() == key:
            return info.tool
    return None


register_tool(ToolInfo(Tool.PENCIL, "Pencil", "p"))
register_tool(ToolInfo(Tool.BRUSH, "Brush", "b"))
register_tool(ToolInfo(Tool.LINE, "Line", "l", draws_shape=True))
register_tool(ToolInfo(Tool.CIRCLE, "Circle", "o", draws_shape=True))
register_tool(ToolInfo(Tool.RECTANGLE, "Rect", "r", draws_shape=True))
register_tool(ToolInfo(Tool.TRIANGLE, "Triangle", "t", draws_shape=True))
register_tool(ToolInfo(Tool.ERASER, "Eraser", "e"))
register_tool(ToolInfo(Tool.SELECT, "Select", "v"))

#: Tools cycled with TAB.
TOOL_CYCLE = [Tool.PENCIL, Tool.BRUSH, Tool.LINE, Tool.CIRCLE,
              Tool.RECTANGLE, Tool.TRIANGLE, Tool.ERASER, Tool.SELECT]

#: Shape tools available for the two-finger SHAPE gesture (cycled with N).
SHAPE_TOOLS = [Tool.CIRCLE, Tool.RECTANGLE, Tool.LINE, Tool.TRIANGLE]


def _noop(*args, **kwargs):
    return None


#: Optional per-tool behavior hooks (future tools attach callables here).
TOOL_BEHAVIORS: Dict[Tool, Dict[str, Callable]] = {}
