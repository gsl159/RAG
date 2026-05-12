"""Tool registry for agentic RAG -- registers and executes named tools.

The ``ToolRegistry`` provides a simple ``execute(name, params)`` interface
that the ``AgentStep`` uses to run tool calls such as calculator and date
parsing.  Tools are registered via the ``@tool`` decorator or by calling
``register()`` directly.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine

ToolFunc = Callable[..., Coroutine[Any, Any, str]]


class ToolRegistry:
    """Registry of named async tool functions.

    Usage::

        registry = ToolRegistry()
        registry.register("calculator", calculator_tool)
        result = await registry.execute("calculator", {"expression": "1+1"})
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolFunc] = {}

    def register(self, name: str, func: ToolFunc) -> None:
        """Register a tool function under *name*.

        Args:
            name: The tool name (used by the agent).
            func: An async callable that receives ``**params`` and returns a
                  string result.
        """
        self._tools[name] = func

    async def execute(self, name: str, params: dict[str, Any] | None = None) -> str:
        """Execute the named tool with *params*.

        Args:
            name: The registered tool name.
            params: Optional keyword arguments forwarded to the tool function.

        Returns:
            The tool result as a string.

        Raises:
            ValueError: If *name* is not a registered tool.
        """
        func = self._tools.get(name)
        if func is None:
            raise ValueError(f"Unknown tool: '{name}'")
        kwargs = dict(params) if params else {}
        return await func(**kwargs)


# ---------------------------------------------------------------------------
# Built-in tools
# ---------------------------------------------------------------------------


async def _calculator(expression: str = "") -> str:
    """Evaluate a simple arithmetic expression.

    Supports ``+``, ``-``, ``*``, ``/``, ``**``, ``%``, ``//``, parentheses,
    and common mathematical constants (``pi``, ``e``).

    Args:
        expression: The mathematical expression to evaluate.

    Returns:
        The formatted result string.
    """
    import math

    safe = expression.strip()
    # Replace human-readable multiplication/division symbols
    safe = safe.replace("×", "*").replace("÷", "/").replace("^", "**")
    # Only allow safe characters
    allowed = r"[\d\s+\-*/().,%pi e]"
    cleaned = "".join(c for c in safe if re.match(allowed, c))

    if not cleaned:
        return "无法解析表达式"

    try:
        # Build a safe namespace with common math functions
        ns = {
            "pi": math.pi,
            "e": math.e,
            "sqrt": math.sqrt,
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
        }
        result = eval(cleaned, {"__builtins__": {}}, ns)  # NOQA: S307
        return f"计算结果：{result}"
    except Exception:
        return "计算失败，请检查表达式"


async def _date_parser(query: str = "") -> str:
    """Parse date-related queries using common Chinese/English patterns.

    Args:
        query: The user's date-related question.

    Returns:
        A human-readable answer string.
    """
    now = datetime.now(timezone.utc)

    # Pattern: X天后 / X day(s) later
    m = re.search(r"(\d+)\s*天(?:后|以[后後])", query)
    if m:
        days = int(m.group(1))
        future = now + timedelta(days=days)
        return f"{days}天后是 {future.strftime('%Y年%m月%d日')}"

    # Pattern: X天前 / X day(s) ago
    m = re.search(r"(\d+)\s*天(?:前|以[前前])", query)
    if m:
        days = int(m.group(1))
        past = now - timedelta(days=days)
        return f"{days}天前是 {past.strftime('%Y年%m月%d日')}"

    # Pattern: 今天几号 / 今天星期几
    if "星期" in query or "周" in query:
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        wd = weekdays[now.weekday()]
        return f"今天是 {now.strftime('%Y年%m月%d日')} 星期{wd}"

    if "几号" in query or "日期" in query:
        return f"今天是 {now.strftime('%Y年%m月%d日')}"

    return f"当前时间：{now.strftime('%Y-%m-%d %H:%M:%S UTC')}"


# ---------------------------------------------------------------------------
# Module-level default registry (pre-populated with built-in tools)
# ---------------------------------------------------------------------------

_default_registry: ToolRegistry | None = None


def get_default_registry() -> ToolRegistry:
    """Return the module-level singleton ``ToolRegistry``."""
    global _default_registry
    if _default_registry is None:
        reg = ToolRegistry()
        reg.register("calculator", _calculator)
        reg.register("date_parser", _date_parser)
        _default_registry = reg
    return _default_registry
