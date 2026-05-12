"""Agentic decision step -- LLM decides whether to retrieve, call tools, or answer directly."""

import asyncio
import re
from typing import Any

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.config.settings import Settings
from app.domain.ports.llm_port import AbstractLLMService


class AgentStep:
    """Agentic decision-making step.

    The agent analyses the user query and chooses one of:
      - **retrieval**: standard RAG retrieval.
      - **tool_call**: execute a tool (calculator, date parser) and return.
      - **direct_answer**: answer from LLM knowledge directly.
      - **clarify**: ask the user for more detail.
      - **refuse**: block the query.
      - **multi_step**: decompose into sub-steps.

    A quick rule-based classifier runs first to avoid LLM calls for trivial
    queries (greetings, maths, date questions).
    """

    _AGENT_DECISION_PROMPT = """你是一个智能问答路由器。根据用户问题、对话历史和可用工具，决定最优的处理策略。

可用工具：
- retrieval: 从知识库检索文档（适用于需要查文档的问题）
- calculator: 数学计算（适用于数字运算）
- date_parser: 日期解析和计算
- direct_answer: 直接回答（适用于常识性问题、闲聊、简单问候）
- clarify: 需要用户澄清（问题太模糊或有歧义）
- refuse: 拒绝回答（超出知识库范围、违规问题）
- multi_step: 需要多步推理（先检索再计算，或需要多次检索）

请以JSON格式返回决策，只输出JSON：
{
  "action": "retrieval|calculator|date_parser|direct_answer|clarify|refuse|multi_step",
  "reason": "简短说明决策原因",
  "tool_params": {},
  "sub_steps": [],
  "clarify_question": "",
  "refuse_reason": ""
}"""

    _CALC_KEYWORDS = ["计算", "等于", "多少钱", "加", "减", "乘", "除"]
    _DATE_KEYWORDS = ["几号", "星期几", "周几", "多少天", "天后", "天前", "工作日"]
    _REFUSE_KEYWORDS = ["写代码", "黑客", "密码破解", "破解", "色情", "赌博"]
    _GREETINGS = ["你好", "hello", "hi", "嗨", "早上好", "谢谢", "再见"]

    _KNOWLEDGE_PATTERNS = [
        r"如何", r"怎么", r"哪些", r"什么", r"命令", r"配置",
        r"安装", r"排查", r"查看", r"how", r"what", r"which",
        r"docker", r"k8s", r"linux", r"command",
    ]

    def __init__(
        self,
        llm: AbstractLLMService,
        tool_registry: Any,
        settings: Settings,
    ) -> None:
        """Initialise with LLM service, tool registry, and settings.

        Args:
            llm: LLM service for agent decisions.
            tool_registry: An object with an ``execute(name, params)`` method
                (e.g. ``ToolRegistry``).
            settings: Application settings (provides ``AGENT_DECISION_TIMEOUT``).
        """
        self._llm = llm
        self._tool_registry = tool_registry
        self._settings = settings

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        action, decision = await self._decide(ctx)
        ctx.agent_action = action

        if action in ("retrieval", "multi_step"):
            return ctx

        tool_action = action
        params = decision.get("tool_params", {})

        if tool_action == "calculator":
            expr = params.get("expression", ctx.query)
            result = await self._tool_registry.execute("calculator", {"expression": expr})
            ctx.answer = result
            ctx.degrade_reason = "AGENT_CALCULATOR"
            ctx.early_exit = True
            return ctx

        if tool_action == "date_parser":
            result = await self._tool_registry.execute("date_parser", {"query": ctx.query})
            ctx.answer = result
            ctx.degrade_reason = "AGENT_DATE_PARSER"
            ctx.early_exit = True
            return ctx

        if tool_action == "direct_answer":
            try:
                answer = await asyncio.wait_for(
                    self._llm.chat(
                        [
                            {
                                "role": "system",
                                "content": "你是企业知识库助手，友好简洁地回复用户。",
                            },
                            {"role": "user", "content": ctx.query},
                        ],
                        temperature=0.5,
                        max_tokens=200,
                    ),
                    timeout=2.0,
                )
                if answer and answer.strip():
                    ctx.answer = answer.strip()
                    ctx.degrade_reason = "AGENT_DIRECT_ANSWER"
                    ctx.early_exit = True
                    return ctx
            except Exception:
                pass
            ctx.agent_action = "retrieval"
            return ctx

        if tool_action == "clarify":
            ctx.answer = decision.get(
                "clarify_question", "您的问题不够明确，能否提供更多细节？"
            )
            ctx.degrade_reason = "AGENT_CLARIFY"
            ctx.early_exit = True
            return ctx

        if tool_action == "refuse":
            ctx.answer = decision.get(
                "refuse_reason", "抱歉，该问题超出知识库的服务范围。"
            )
            ctx.degrade_reason = "AGENT_REFUSE"
            ctx.early_exit = True
            return ctx

        ctx.agent_action = "retrieval"
        return ctx

    async def _decide(self, ctx: PipelineContext) -> tuple[str, dict[str, Any]]:
        quick = self._quick_classify(ctx.query)
        if quick is not None:
            return quick, {"action": quick, "reason": "quick_classify"}

        decision = await self._agent_decide(ctx)
        action = decision.get("action", "retrieval")

        valid = {
            "retrieval", "calculator", "date_parser",
            "direct_answer", "clarify", "refuse", "multi_step",
        }
        if action not in valid:
            action = "retrieval"

        if action == "direct_answer" and self._is_knowledge_query(ctx.query):
            action = "retrieval"
            decision["reason"] = "guardrail_force_retrieval"

        return action, decision

    def _quick_classify(self, query: str) -> str | None:
        q = query.strip().lower()
        cleaned = re.sub(r"[计算等于多少求\s?？=]", "", q)
        if re.match(r"^[\d+\-*/()\.\^%×÷√]+$", cleaned) and len(cleaned) > 2:
            return "calculator"
        if len(q) < 10 and any(kw in q for kw in self._GREETINGS):
            return "direct_answer"
        if any(kw in q for kw in self._DATE_KEYWORDS):
            if re.search(r"\d{4}[年\-/]\d{1,2}|\d+\s*[天日](?:后|前)", q):
                return "date_parser"
        if any(kw in q for kw in self._REFUSE_KEYWORDS):
            return "refuse"
        return None

    async def _agent_decide(self, ctx: PipelineContext) -> dict[str, Any]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._AGENT_DECISION_PROMPT},
        ]
        user_content = f"用户问题：{ctx.rewritten_query or ctx.query}"
        if ctx.history:
            recent = ctx.history[-4:]
            hist_text = "\n".join(
                f"{'用户' if m['role'] == 'user' else '助手'}：{m['content'][:200]}"
                for m in recent
            )
            user_content = f"最近对话：\n{hist_text}\n\n{user_content}"
        messages.append({"role": "user", "content": user_content})

        try:
            result = await asyncio.wait_for(
                self._llm.chat_json(messages),
                timeout=self._settings.AGENT_DECISION_TIMEOUT,
            )
            if isinstance(result, dict):
                return result
            return {"action": "retrieval", "reason": "non_dict_response"}
        except asyncio.TimeoutError:
            return {"action": "retrieval", "reason": "decision_timeout"}
        except Exception:
            return {"action": "retrieval", "reason": "decision_error"}

    @staticmethod
    def _is_knowledge_query(query: str) -> bool:
        q = (query or "").strip().lower()
        if not q or len(q) < 8:
            return False
        return any(re.search(p, q) for p in AgentStep._KNOWLEDGE_PATTERNS)
