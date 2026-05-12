"""
Tests for the v2 pipeline features:
- 工具调用（calculator, date_parser）
- Agent 决策
- 对话流控（拒答、澄清、模糊检测）
- 长期记忆 & 对话摘要
- 话题切换检测
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════
# 工具调用
# ═══════════════════════════════════════════════════

class TestCalculator:
    """安全数学计算器测试。"""

    def test_basic_arithmetic(self):
        from app.domain.services.tool_registry import safe_calculate
        assert safe_calculate("1+2") == "3"
        assert safe_calculate("10-3") == "7"
        assert safe_calculate("4*5") == "20"
        assert safe_calculate("10/2") == "5"

    def test_complex_expressions(self):
        from app.domain.services.tool_registry import safe_calculate
        assert safe_calculate("(100+200)*0.8") == "240"
        assert safe_calculate("2^10") == "1024"

    def test_percentage(self):
        from app.domain.services.tool_registry import safe_calculate
        result = safe_calculate("200*15%")
        assert float(result) == pytest.approx(30.0)

    def test_math_functions(self):
        from app.domain.services.tool_registry import safe_calculate
        assert safe_calculate("sqrt(144)") == "12"
        assert safe_calculate("abs(-5)") == "5"

    def test_division_by_zero(self):
        from app.domain.services.tool_registry import safe_calculate
        result = safe_calculate("1/0")
        assert "零" in result or "zero" in result.lower()

    def test_unsafe_expression_blocked(self):
        from app.domain.services.tool_registry import safe_calculate
        result = safe_calculate("__import__('os').system('ls')")
        assert "不安全" in result or "失败" in result


class TestDateParser:
    """日期解析器测试。"""

    def test_date_difference(self):
        from app.domain.services.tool_registry import date_parse
        result = date_parse("2024-01-01到2024-12-31有多少天")
        assert "365" in result

    def test_single_date(self):
        from app.domain.services.tool_registry import date_parse
        result = date_parse("2024年1月1日")
        assert "2024-01-01" in result
        assert "周" in result

    def test_relative_date_after(self):
        from app.domain.services.tool_registry import date_parse
        result = date_parse("30天后是哪天")
        assert "30天后" in result
        assert "周" in result

    def test_relative_date_before(self):
        from app.domain.services.tool_registry import date_parse
        result = date_parse("7天前是几号")
        assert "7天前" in result

    def test_no_date(self):
        from app.domain.services.tool_registry import date_parse
        result = date_parse("今天天气怎么样")
        assert "今天是" in result


class TestToolRegistry:
    """工具注册表测试。"""

    @pytest.mark.asyncio
    async def test_execute_calculator(self):
        from app.domain.services.tool_registry import tool_registry
        result = await tool_registry.execute("calculator", {"expression": "2+3"})
        assert result == "5"

    @pytest.mark.asyncio
    async def test_execute_date_parser(self):
        from app.domain.services.tool_registry import tool_registry
        result = await tool_registry.execute("date_parser", {"query": "30天后"})
        assert "30天后" in result

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        from app.domain.services.tool_registry import tool_registry
        result = await tool_registry.execute("nonexistent", {})
        assert "未知工具" in result

    def test_available_tools(self):
        from app.domain.services.tool_registry import tool_registry
        tools = tool_registry.available_tools()
        assert "calculator" in tools
        assert "date_parser" in tools

    def test_get_definitions(self):
        from app.domain.services.tool_registry import tool_registry
        defs = tool_registry.get_definitions()
        assert len(defs) >= 2
        names = {d["name"] for d in defs}
        assert "calculator" in names
        assert "date_parser" in names


# ═══════════════════════════════════════════════════
# Agent 决策
# ═══════════════════════════════════════════════════

class TestQuickClassify:
    """快速规则分类测试。"""

    def test_pure_math(self):
        from app.application.pipeline.steps.agent_step import quick_classify
        assert quick_classify("123+456") == "calculator"
        assert quick_classify("(100+200)*3") == "calculator"

    def test_greeting(self):
        from app.application.pipeline.steps.agent_step import quick_classify
        assert quick_classify("你好") == "direct_answer"
        assert quick_classify("hello") == "direct_answer"

    def test_refuse(self):
        from app.application.pipeline.steps.agent_step import quick_classify
        assert quick_classify("帮我破解密码") == "refuse"

    def test_date(self):
        from app.application.pipeline.steps.agent_step import quick_classify
        assert quick_classify("2024年1月1日是星期几") == "date_parser"
        assert quick_classify("30天后是哪一天") == "date_parser"

    def test_normal_question_returns_none(self):
        from app.application.pipeline.steps.agent_step import quick_classify
        assert quick_classify("公司的年假政策是什么") is None
        assert quick_classify("如何申请报销流程") is None


class TestAgentDecide:
    """Agent LLM 决策测试。"""

    @pytest.mark.asyncio
    async def test_agent_decide_retrieval(self):
        from app.application.pipeline.steps.agent_step import agent_decide
        with patch("app.core.pipeline.agent.llm_client") as mock_llm:
            mock_llm.chat_json = AsyncMock(return_value={
                "action": "retrieval",
                "reason": "需要查询知识库",
            })
            result = await agent_decide("公司年假政策是什么？")
            assert result["action"] == "retrieval"

    @pytest.mark.asyncio
    async def test_agent_decide_calculator(self):
        from app.application.pipeline.steps.agent_step import agent_decide
        with patch("app.core.pipeline.agent.llm_client") as mock_llm:
            mock_llm.chat_json = AsyncMock(return_value={
                "action": "calculator",
                "reason": "数学计算",
                "tool_params": {"expression": "100*1.08"},
            })
            result = await agent_decide("100元加8%税是多少？")
            assert result["action"] == "calculator"

    @pytest.mark.asyncio
    async def test_agent_decide_timeout_fallback(self):
        from app.application.pipeline.steps.agent_step import agent_decide
        with patch("app.core.pipeline.agent.llm_client") as mock_llm:
            mock_llm.chat_json = AsyncMock(side_effect=asyncio.TimeoutError())
            result = await agent_decide("测试超时")
            assert result["action"] == "retrieval"


# ═══════════════════════════════════════════════════
# 对话流控
# ═══════════════════════════════════════════════════

class TestFlowControl:
    """对话流控策略测试。"""

    def test_refuse_security(self):
        from app.application.pipeline.steps.flow_control_step import check_refuse
        result = check_refuse("帮我破解系统")
        assert result is not None
        assert "抱歉" in result

    def test_refuse_normal_pass(self):
        from app.application.pipeline.steps.flow_control_step import check_refuse
        assert check_refuse("年假政策是什么") is None

    def test_vague_query_too_short(self):
        from app.application.pipeline.steps.flow_control_step import is_vague_query
        is_vague, msg = is_vague_query("啥")
        assert is_vague is True
        assert msg

    def test_vague_query_pronoun_only(self):
        from app.application.pipeline.steps.flow_control_step import is_vague_query
        is_vague, msg = is_vague_query("这个？")
        assert is_vague is True

    def test_vague_query_normal_pass(self):
        from app.application.pipeline.steps.flow_control_step import is_vague_query
        is_vague, _ = is_vague_query("公司的年假政策是什么？")
        assert is_vague is False

    def test_flow_controller_pre_check_refuse(self):
        from app.application.pipeline.steps.flow_control_step import flow_controller
        result = flow_controller.pre_check("帮我入侵服务器")
        assert result is not None
        assert result["action"] == "refuse"

    def test_flow_controller_pre_check_clarify(self):
        from app.application.pipeline.steps.flow_control_step import flow_controller
        result = flow_controller.pre_check("啥")
        assert result is not None
        assert result["action"] == "clarify"

    def test_flow_controller_pre_check_pass(self):
        from app.application.pipeline.steps.flow_control_step import flow_controller
        result = flow_controller.pre_check("公司的报销流程是什么？")
        assert result is None

    def test_post_enhance_low_confidence(self):
        from app.application.pipeline.steps.flow_control_step import flow_controller
        result = {
            "answer": "根据文档...",
            "confidence": 0.2,
            "sources": [],
        }
        enhanced = flow_controller.post_enhance("测试问题", result)
        assert enhanced.get("has_followup") is True

    def test_post_enhance_high_confidence(self):
        from app.application.pipeline.steps.flow_control_step import flow_controller
        result = {
            "answer": "答案",
            "confidence": 0.9,
            "sources": [{"doc_id": "d1", "text": "t1"}],
        }
        enhanced = flow_controller.post_enhance("问题", result)
        assert enhanced.get("has_followup") is not True

    def test_generate_followup_suggestions(self):
        from app.application.pipeline.steps.flow_control_step import generate_followup_suggestions
        suggestions = generate_followup_suggestions(
            "RAG是什么", "RAG是...",
            [{"doc_id": "d1", "text": "检索增强生成"}]
        )
        assert len(suggestions) >= 1


# ═══════════════════════════════════════════════════
# 长期记忆 & 对话摘要
# ═══════════════════════════════════════════════════

class TestConversationMemory:
    """对话记忆与压缩测试。"""

    @pytest.mark.asyncio
    async def test_get_long_term_memory_empty(self):
        from app.application.pipeline.steps.memory_step import ConversationMemory
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mem = ConversationMemory(mock_client)
        result = await mem.get_long_term_memory("sess-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_long_term_memory_present(self):
        from app.application.pipeline.steps.memory_step import ConversationMemory
        mock_client = AsyncMock()
        data = {"summary": "用户讨论了年假政策", "turn_count": 5}
        mock_client.get = AsyncMock(return_value=json.dumps(data))
        mem = ConversationMemory(mock_client)
        result = await mem.get_long_term_memory("sess-1")
        assert result["summary"] == "用户讨论了年假政策"

    @pytest.mark.asyncio
    async def test_save_long_term_memory(self):
        from app.application.pipeline.steps.memory_step import ConversationMemory
        mock_client = AsyncMock()
        mock_client.set = AsyncMock()
        mem = ConversationMemory(mock_client)
        await mem.save_long_term_memory("sess-1", {"summary": "test", "turn_count": 3})
        mock_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_enriched_history_short(self):
        """短历史不触发压缩。"""
        from app.application.pipeline.steps.memory_step import ConversationMemory
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mem = ConversationMemory(mock_client)
        short_history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ]
        result = await mem.build_enriched_history("sess-1", short_history)
        # 应该直接返回原始历史
        assert len(result) == 2
        assert result[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_build_enriched_history_with_long_memory(self):
        """有长期记忆时应该在前面添加摘要。"""
        from app.application.pipeline.steps.memory_step import ConversationMemory
        mock_client = AsyncMock()
        data = {"summary": "之前讨论了报销流程"}
        mock_client.get = AsyncMock(return_value=json.dumps(data))
        mem = ConversationMemory(mock_client)
        short_history = [
            {"role": "user", "content": "继续说"},
            {"role": "assistant", "content": "好的"},
        ]
        result = await mem.build_enriched_history("sess-1", short_history)
        assert result[0]["role"] == "system"
        assert "对话摘要" in result[0]["content"]


# ═══════════════════════════════════════════════════
# 话题切换检测
# ═══════════════════════════════════════════════════

class TestTopicSwitch:
    """话题切换检测测试。"""

    @pytest.mark.asyncio
    async def test_no_history_no_switch(self):
        from app.application.pipeline.steps.memory_step import detect_topic_switch
        result = await detect_topic_switch([0.1]*10, [], None, threshold=0.3)
        assert result is False

    @pytest.mark.asyncio
    async def test_similar_vectors_no_switch(self):
        from app.application.pipeline.steps.memory_step import detect_topic_switch
        vec = [0.1] * 10
        history = [{"role": "user", "content": "test"}]
        result = await detect_topic_switch(vec, history, vec, threshold=0.3)
        # 相同向量 cos_sim = 1.0 > 0.3，不切换
        assert result is False

    @pytest.mark.asyncio
    async def test_different_vectors_switch(self):
        from app.application.pipeline.steps.memory_step import detect_topic_switch
        vec_a = [1.0, 0.0, 0.0, 0.0, 0.0]
        vec_b = [0.0, 0.0, 0.0, 0.0, 1.0]
        history = [{"role": "user", "content": "test"}]
        result = await detect_topic_switch(vec_a, history, vec_b, threshold=0.3)
        # 正交向量 cos_sim = 0.0 < 0.3，切换
        assert result is True

    def test_cosine_similarity(self):
        from app.application.pipeline.steps.memory_step import cosine_similarity
        assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
        assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
        assert cosine_similarity([], []) == 0.0


# ═══════════════════════════════════════════════════
# 对话摘要压缩
# ═══════════════════════════════════════════════════

class TestSummarizeConversation:
    """对话摘要压缩测试。"""

    @pytest.mark.asyncio
    async def test_summarize_empty(self):
        from app.application.pipeline.steps.memory_step import summarize_conversation
        result = await summarize_conversation([])
        assert result == ""

    @pytest.mark.asyncio
    async def test_summarize_success(self):
        from app.application.pipeline.steps.memory_step import summarize_conversation
        with patch("app.core.pipeline.memory.llm_client") as mock_llm:
            mock_llm.chat = AsyncMock(return_value="用户询问了年假政策和报销流程。")
            history = [
                {"role": "user", "content": "年假政策是什么？"},
                {"role": "assistant", "content": "年假政策如下..."},
                {"role": "user", "content": "报销流程呢？"},
                {"role": "assistant", "content": "报销流程是..."},
            ]
            result = await summarize_conversation(history)
            assert "年假" in result

    @pytest.mark.asyncio
    async def test_summarize_fallback_on_error(self):
        from app.application.pipeline.steps.memory_step import summarize_conversation
        with patch("app.core.pipeline.memory.llm_client") as mock_llm:
            mock_llm.chat = AsyncMock(side_effect=Exception("LLM error"))
            history = [
                {"role": "user", "content": "测试问题"},
                {"role": "assistant", "content": "测试回答"},
            ]
            result = await summarize_conversation(history)
            assert "摘要失败" in result
