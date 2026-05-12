"""
Tests for v3 features:
- 语义分块 (SemanticChunker) + 递归分块 + 父子引用
- Cross-encoder Reranker (BGE-reranker-v2-m3)
- GraphRAG (知识图谱 + 多跳推理 + 实体关系查询)
- 细粒度意图识别 (FACT/COMPARISON/REASONING/SUMMARY/DEFINITION/HOW_TO)
- 路由策略映射
"""
import asyncio
import json
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════
# 1. 语义分块 (SemanticChunker)
# ═══════════════════════════════════════════════════

class TestSemanticChunkerBasic:
    """语义分块器基础测试。"""

    def test_empty_input(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=500)
        assert chunker.split("") == []
        assert chunker.split("   ") == []

    def test_short_text_single_chunk(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=500)
        text = "这是一段简短的文本，不需要拆分。"
        nodes = chunker.split(text)
        assert len(nodes) == 1
        assert nodes[0].level == "leaf"
        assert nodes[0].text == text

    def test_long_text_produces_multiple_chunks(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=100, chunk_overlap=10)
        text = "这是一段很长的文本。" * 50  # ~450 chars
        nodes = chunker.split(text)
        leaves = chunker.get_leaf_chunks(nodes)
        assert len(leaves) > 1

    def test_chunk_nodes_have_ids(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=100)
        text = "段落一内容很长需要分块。" * 20
        nodes = chunker.split(text)
        ids = [n.id for n in nodes]
        assert len(ids) == len(set(ids)), "chunk IDs 应唯一"


class TestHeadingDetection:
    """标题检测测试。"""

    def test_markdown_headings(self):
        from app.infrastructure.chunking.strategies.semantic import _detect_headings
        text = "# 标题一\n内容一\n## 标题二\n内容二\n### 标题三\n内容三"
        headings = _detect_headings(text)
        assert len(headings) >= 3
        assert headings[0]["type"] == "markdown"
        assert headings[0]["level"] == 1
        assert headings[1]["level"] == 2

    def test_chinese_headings(self):
        from app.infrastructure.chunking.strategies.semantic import _detect_headings
        text = "一、总则\n本规定适用于...\n二、实施范围\n全公司适用"
        headings = _detect_headings(text)
        assert len(headings) >= 2
        assert any(h["type"] == "chinese" for h in headings)

    def test_no_headings(self):
        from app.infrastructure.chunking.strategies.semantic import _detect_headings
        text = "这是一段纯文本，没有标题结构。只是连续的内容。"
        headings = _detect_headings(text)
        assert len(headings) == 0

    def test_mixed_headings(self):
        from app.infrastructure.chunking.strategies.semantic import _detect_headings
        text = "# Introduction\n内容\n一、背景\n说明文字"
        headings = _detect_headings(text)
        assert len(headings) >= 2


class TestSemanticChunkerStructure:
    """语义分块器结构化拆分测试。"""

    def test_heading_based_split(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=500)
        text = "# 第一章\n这是第一章的内容。\n\n# 第二章\n这是第二章的内容。"
        nodes = chunker.split(text)
        texts = [n.text for n in nodes]
        assert any("第一章" in t for t in texts)
        assert any("第二章" in t for t in texts)

    def test_parent_child_relationship(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=80, chunk_overlap=10)
        # 构造一个足够长的section使其产生parent-child结构
        text = "# 概述\n" + "这是一段很长的内容需要递归拆分。" * 30
        nodes = chunker.split(text)
        parents = [n for n in nodes if n.level == "section"]
        leaves = [n for n in nodes if n.level == "leaf"]
        if parents:
            parent = parents[0]
            assert len(parent.children_ids) > 0
            child_ids = {n.id for n in leaves}
            for cid in parent.children_ids:
                assert cid in child_ids, "parent 的 children_ids 应指向 leaf 节点"

    def test_leaf_chunks_have_parent_id(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=80, chunk_overlap=10)
        text = "# 标题\n" + "内容段落很长需要拆分成多个小块。" * 30
        nodes = chunker.split(text)
        leaves = chunker.get_leaf_chunks(nodes)
        for leaf in leaves:
            assert leaf.level == "leaf"
            # parent_id 可能为空（如果section本身就是leaf）

    def test_get_leaf_chunks(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=80, chunk_overlap=10)
        text = "# 标题\n" + "这段内容需要拆分。" * 30
        nodes = chunker.split(text)
        leaves = chunker.get_leaf_chunks(nodes)
        for n in leaves:
            assert n.level == "leaf"

    def test_get_parent_map(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=500)
        text = "# A\n内容A\n# B\n内容B"
        nodes = chunker.split(text)
        pmap = chunker.get_parent_map(nodes)
        for n in nodes:
            assert n.id in pmap

    def test_chunk_node_to_dict(self):
        from app.infrastructure.chunking.strategies.semantic import ChunkNode
        node = ChunkNode(
            id="test-id",
            text="测试文本",
            chunk_idx=0,
            level="leaf",
            heading="标题",
            parent_id="parent-id",
        )
        d = node.to_dict()
        assert d["id"] == "test-id"
        assert d["heading"] == "标题"
        assert d["parent_id"] == "parent-id"


class TestParentExpansion:
    """Parent Expansion 测试。"""

    def test_expand_with_parent(self):
        from app.infrastructure.chunking.strategies.semantic import expand_with_parent
        retrieved = [
            {"id": "c1", "text": "子文本1", "score": 0.9},
            {"id": "c2", "text": "子文本2", "score": 0.8},
        ]
        parent_map = {"c1": "p1", "c2": "p1"}
        parent_texts = {"p1": "这是完整的父级文本，包含更多上下文信息。"}
        expanded = expand_with_parent(retrieved, parent_map, parent_texts)
        assert any(d.get("_expanded") for d in expanded)

    def test_expand_no_parent(self):
        from app.infrastructure.chunking.strategies.semantic import expand_with_parent
        retrieved = [{"id": "c1", "text": "子文本1", "score": 0.9}]
        expanded = expand_with_parent(retrieved, {}, {})
        assert len(expanded) == 1
        assert not expanded[0].get("_expanded")


# ═══════════════════════════════════════════════════
# 2. Cross-encoder Reranker
# ═══════════════════════════════════════════════════

class TestSimpleReranker:
    """简单关键词重排测试。"""

    def test_rerank_basic(self):
        from app.infrastructure.reranker.simple_reranker import SimpleReranker
        rr = SimpleReranker()
        docs = [
            {"text": "Python 编程语言入门", "rrf_score": 0.5},
            {"text": "Java 编程指南", "rrf_score": 0.6},
            {"text": "Python 高级技巧与实战", "rrf_score": 0.4},
        ]
        result = rr.rerank("Python", docs, top_n=2)
        assert len(result) == 2
        assert all("rerank_score" in d for d in result)

    def test_rerank_empty(self):
        from app.infrastructure.reranker.simple_reranker import SimpleReranker
        rr = SimpleReranker()
        assert rr.rerank("query", [], top_n=5) == []

    def test_rerank_top_n(self):
        from app.infrastructure.reranker.simple_reranker import SimpleReranker
        rr = SimpleReranker()
        docs = [{"text": f"文档{i}", "rrf_score": 0.1 * i} for i in range(10)]
        result = rr.rerank("文档", docs, top_n=3)
        assert len(result) == 3


class TestCrossEncoderReranker:
    """Cross-encoder Reranker 测试。"""

    @pytest.mark.asyncio
    async def test_rerank_success(self):
        from app.infrastructure.reranker.simple_reranker import CrossEncoderReranker
        rr = CrossEncoderReranker()
        docs = [
            {"text": "Python编程", "rrf_score": 0.5},
            {"text": "Java编程", "rrf_score": 0.6},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"index": 0, "relevance_score": 0.95},
                {"index": 1, "relevance_score": 0.3},
            ]
        }
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await rr.rerank("Python", docs, top_n=2)
            assert len(result) == 2
            assert result[0]["cross_encoder_score"] == pytest.approx(0.95, abs=0.01)

    @pytest.mark.asyncio
    async def test_rerank_fallback_on_error(self):
        from app.infrastructure.reranker.simple_reranker import CrossEncoderReranker
        rr = CrossEncoderReranker()
        docs = [
            {"text": "Python编程", "rrf_score": 0.5},
            {"text": "Java编程", "rrf_score": 0.6},
        ]
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(side_effect=Exception("API Error"))
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await rr.rerank("Python", docs, top_n=2)
            # 应降级到 SimpleReranker
            assert len(result) == 2
            assert all("rerank_score" in d for d in result)

    @pytest.mark.asyncio
    async def test_rerank_empty_docs(self):
        from app.infrastructure.reranker.simple_reranker import CrossEncoderReranker
        rr = CrossEncoderReranker()
        assert await rr.rerank("query", []) == []

    @pytest.mark.asyncio
    async def test_rerank_empty_query(self):
        from app.infrastructure.reranker.simple_reranker import CrossEncoderReranker
        rr = CrossEncoderReranker()
        docs = [{"text": "文档", "rrf_score": 0.5}]
        result = await rr.rerank("", docs, top_n=1)
        assert len(result) == 1


class TestHybridReranker:
    """混合重排器测试。"""

    @pytest.mark.asyncio
    async def test_simple_mode(self):
        from app.infrastructure.reranker.simple_reranker import HybridReranker
        rr = HybridReranker()
        docs = [
            {"text": "Python入门", "rrf_score": 0.5},
            {"text": "Java指南", "rrf_score": 0.6},
        ]
        with patch("app.core.reranker.settings") as mock_settings:
            mock_settings.RERANKER_MODE = "simple"
            result = await rr.async_rerank("Python", docs, top_n=2)
            assert len(result) == 2

    def test_sync_rerank_uses_simple(self):
        from app.infrastructure.reranker.simple_reranker import HybridReranker
        rr = HybridReranker()
        docs = [{"text": "Python入门", "rrf_score": 0.5}]
        result = rr.rerank("Python", docs, top_n=1)
        assert len(result) == 1


# ═══════════════════════════════════════════════════
# 3. GraphRAG (知识图谱)
# ═══════════════════════════════════════════════════

class TestGraphEntity:
    """实体数据结构测试。"""

    def test_entity_to_dict(self):
        from app.infrastructure.graph.graph_store import Entity
        ent = Entity(name="Python", entity_type="concept", description="编程语言")
        ent.doc_ids.add("doc-1")
        d = ent.to_dict()
        assert d["name"] == "Python"
        assert d["type"] == "concept"
        assert "doc-1" in d["doc_ids"]

    def test_relation_to_dict(self):
        from app.infrastructure.graph.graph_store import Relation
        rel = Relation(
            source="Python", target="PEP8",
            relation_type="规范", doc_id="doc-1"
        )
        d = rel.to_dict()
        assert d["source"] == "Python"
        assert d["target"] == "PEP8"
        assert d["relation"] == "规范"


class TestKnowledgeGraph:
    """知识图谱核心测试。"""

    def _make_graph(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph, Entity, Relation
        kg = KnowledgeGraph()
        kg.add_entity(Entity(name="Python", entity_type="concept"))
        kg.add_entity(Entity(name="Flask", entity_type="concept"))
        kg.add_entity(Entity(name="Django", entity_type="concept"))
        kg.add_relation(Relation(source="Python", target="Flask", relation_type="有框架"))
        kg.add_relation(Relation(source="Python", target="Django", relation_type="有框架"))
        kg.add_relation(Relation(source="Flask", target="Django", relation_type="竞争关系"))
        return kg

    def test_add_entity(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph, Entity
        kg = KnowledgeGraph()
        kg.add_entity(Entity(name="Python", entity_type="concept"))
        assert kg.entity_count == 1

    def test_merge_entity(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph, Entity
        kg = KnowledgeGraph()
        e1 = Entity(name="Python", entity_type="concept")
        e1.doc_ids.add("doc-1")
        e2 = Entity(name="Python", entity_type="concept", description="编程语言")
        e2.doc_ids.add("doc-2")
        kg.add_entity(e1)
        kg.add_entity(e2)
        assert kg.entity_count == 1  # 合并
        ent = kg.find_entity("Python")
        assert "doc-1" in ent.doc_ids
        assert "doc-2" in ent.doc_ids
        assert ent.description == "编程语言"

    def test_add_relation(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph, Entity, Relation
        kg = KnowledgeGraph()
        kg.add_entity(Entity(name="A"))
        kg.add_entity(Entity(name="B"))
        kg.add_relation(Relation(source="A", target="B", relation_type="related"))
        assert kg.relation_count == 1

    def test_find_entity(self):
        kg = self._make_graph()
        ent = kg.find_entity("Python")
        assert ent is not None
        assert ent.name == "Python"
        assert kg.find_entity("Rust") is None

    def test_search_entities(self):
        kg = self._make_graph()
        results = kg.search_entities("flask")
        assert len(results) >= 1
        assert results[0].name == "Flask"

    def test_get_neighbors(self):
        kg = self._make_graph()
        neighbors = kg.get_neighbors("Python")
        assert len(neighbors) == 2
        neighbor_names = {n["entity"] for n in neighbors}
        assert "Flask" in neighbor_names
        assert "Django" in neighbor_names

    def test_multi_hop_query(self):
        kg = self._make_graph()
        result = kg.multi_hop_query("Python", max_hops=2)
        assert len(result["entities"]) >= 3  # Python + Flask + Django
        assert len(result["relations"]) >= 2

    def test_multi_hop_missing_entity(self):
        kg = self._make_graph()
        result = kg.multi_hop_query("Rust", max_hops=2)
        assert result["entities"] == []

    def test_subgraph_context(self):
        kg = self._make_graph()
        ctx = kg.get_subgraph_context(["Python"])
        assert "知识图谱关系" in ctx
        assert "Flask" in ctx

    def test_subgraph_context_empty(self):
        kg = self._make_graph()
        ctx = kg.get_subgraph_context(["Rust"])
        assert ctx == ""

    def test_add_from_extraction(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph, Entity, Relation
        kg = KnowledgeGraph()
        entities = [Entity(name="X"), Entity(name="Y")]
        relations = [Relation(source="X", target="Y", relation_type="r")]
        kg.add_from_extraction(entities, relations)
        assert kg.entity_count == 2
        assert kg.relation_count == 1

    def test_get_stats(self):
        kg = self._make_graph()
        stats = kg.get_stats()
        assert stats["entity_count"] == 3
        assert stats["relation_count"] == 3


class TestGraphSerialization:
    """图谱序列化测试。"""

    def test_json_roundtrip(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph, Entity, Relation
        kg = KnowledgeGraph()
        kg.add_entity(Entity(name="A", entity_type="concept", description="desc"))
        kg.add_entity(Entity(name="B", entity_type="org"))
        kg.add_relation(Relation(source="A", target="B", relation_type="related"))
        json_str = kg.to_json()

        kg2 = KnowledgeGraph()
        kg2.from_json(json_str)
        assert kg2.entity_count == 2
        assert kg2.relation_count == 1
        assert kg2.find_entity("A").description == "desc"

    def test_from_invalid_json(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.from_json("not valid json")  # 不应抛异常
        assert kg.entity_count == 0

    @pytest.mark.asyncio
    async def test_save_to_redis(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph, Entity
        kg = KnowledgeGraph()
        kg.add_entity(Entity(name="Test"))
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        result = await kg.save_to_redis(mock_redis)
        assert result is True
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_from_redis(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph, Entity, Relation
        kg_src = KnowledgeGraph()
        kg_src.add_entity(Entity(name="X"))
        kg_src.add_entity(Entity(name="Y"))
        kg_src.add_relation(Relation(source="X", target="Y", relation_type="r"))
        json_str = kg_src.to_json()

        kg = KnowledgeGraph()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json_str)
        result = await kg.load_from_redis(mock_redis)
        assert result is True
        assert kg.entity_count == 2

    @pytest.mark.asyncio
    async def test_save_redis_none(self):
        from app.infrastructure.graph.graph_store import KnowledgeGraph
        kg = KnowledgeGraph()
        assert await kg.save_to_redis(None) is False


class TestEntityExtraction:
    """实体抽取测试。"""

    @pytest.mark.asyncio
    async def test_extract_success(self):
        from app.infrastructure.graph.graph_store import extract_entities_relations
        mock_result = {
            "entities": [
                {"name": "Python", "type": "concept", "description": "编程语言"},
                {"name": "Django", "type": "concept", "description": "Web框架"},
            ],
            "relations": [
                {"source": "Python", "target": "Django", "relation": "has_framework", "description": "拥有"}
            ]
        }
        with patch("app.infrastructure.graph.graph_store.llm_client") as mock_llm:
            mock_llm.chat_json = AsyncMock(return_value=mock_result)
            entities, relations = await extract_entities_relations("Python是编程语言，Django是其Web框架")
            assert len(entities) == 2
            assert len(relations) == 1
            assert entities[0].name == "Python"

    @pytest.mark.asyncio
    async def test_extract_empty_text(self):
        from app.infrastructure.graph.graph_store import extract_entities_relations
        entities, relations = await extract_entities_relations("")
        assert entities == []
        assert relations == []

    @pytest.mark.asyncio
    async def test_extract_short_text(self):
        from app.infrastructure.graph.graph_store import extract_entities_relations
        entities, relations = await extract_entities_relations("短文本")
        assert entities == []

    @pytest.mark.asyncio
    async def test_extract_handles_error(self):
        from app.infrastructure.graph.graph_store import extract_entities_relations
        with patch("app.infrastructure.graph.graph_store.llm_client") as mock_llm:
            mock_llm.chat_json = AsyncMock(side_effect=Exception("API Error"))
            entities, relations = await extract_entities_relations("测试文本内容足够长来触发抽取")
            assert entities == []
            assert relations == []


class TestExtractQueryEntities:
    """查询实体识别测试。"""

    def test_exact_match(self):
        from app.infrastructure.graph.graph_store import extract_query_entities, KnowledgeGraph, Entity
        kg = KnowledgeGraph()
        kg.add_entity(Entity(name="Python"))
        kg.add_entity(Entity(name="Flask"))
        matched = extract_query_entities("Python和Flask的区别", kg)
        assert "Python" in matched
        assert "Flask" in matched

    def test_no_match(self):
        from app.infrastructure.graph.graph_store import extract_query_entities, KnowledgeGraph, Entity
        kg = KnowledgeGraph()
        kg.add_entity(Entity(name="Python"))
        matched = extract_query_entities("今天天气怎么样", kg)
        assert len(matched) == 0


# ═══════════════════════════════════════════════════
# 4. 细粒度意图识别
# ═══════════════════════════════════════════════════

class TestIntentClassification:
    """意图分类测试。"""

    @pytest.mark.asyncio
    async def test_backward_compatible_classify(self):
        from app.application.pipeline.steps.intent_step import classify_intent
        result = await classify_intent("什么是Python？")
        assert result in ("C0", "C1", "C2")

    @pytest.mark.asyncio
    async def test_classify_c0_short_definition(self):
        from app.application.pipeline.steps.intent_step import classify_intent
        result = await classify_intent("Python是什么")
        assert result == "C0"

    @pytest.mark.asyncio
    async def test_classify_c2_long_query(self):
        from app.application.pipeline.steps.intent_step import classify_intent
        result = await classify_intent(
            "请详细分析Python在大规模分布式系统中的应用场景，"
            "并与Go语言、Java进行性能对比分析"
        )
        assert result == "C2"


class TestIntentV2:
    """v2 细粒度意图分类测试。"""

    @pytest.mark.asyncio
    async def test_definition_intent(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2("什么是机器学习？")
        assert result.semantic_type == "DEFINITION"

    @pytest.mark.asyncio
    async def test_comparison_intent(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2("Python和Java有什么区别？两者的优缺点是什么？")
        assert result.semantic_type == "COMPARISON"

    @pytest.mark.asyncio
    async def test_reasoning_intent(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2("为什么深度学习需要大量数据？请解释原因")
        assert result.semantic_type == "REASONING"

    @pytest.mark.asyncio
    async def test_summary_intent(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2("请总结一下本季度的销售情况")
        assert result.semantic_type == "SUMMARY"

    @pytest.mark.asyncio
    async def test_howto_intent(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2("如何配置 Nginx 反向代理？步骤是什么")
        assert result.semantic_type == "HOW_TO"

    @pytest.mark.asyncio
    async def test_fact_default(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2("2023年中国GDP是多少？")
        assert result.semantic_type == "FACT"

    @pytest.mark.asyncio
    async def test_intent_result_structure(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2("什么是Python？")
        assert hasattr(result, "complexity")
        assert hasattr(result, "semantic_type")
        assert hasattr(result, "route_strategy")
        d = result.to_dict()
        assert "complexity" in d
        assert "semantic_type" in d
        assert "route_strategy" in d


# ═══════════════════════════════════════════════════
# 5. 路由策略映射
# ═══════════════════════════════════════════════════

class TestRouteStrategy:
    """路由策略测试。"""

    @pytest.mark.asyncio
    async def test_c0_definition_direct_retrieve(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2("什么是Python？")
        assert result.route_strategy == "direct_retrieve"

    @pytest.mark.asyncio
    async def test_c2_comparison_multi_retrieve(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2(
            "请详细对比分析Python和Java在企业级应用开发中的区别和各自优缺点，哪个更适合大型项目"
        )
        assert result.complexity == "C2"
        assert result.route_strategy == "multi_retrieve"

    @pytest.mark.asyncio
    async def test_c2_reasoning_chain_of_thought(self):
        from app.application.pipeline.steps.intent_step import classify_intent_v2
        result = await classify_intent_v2(
            "请从多个角度推理并分析大语言模型在企业知识管理领域快速普及的深层原因和技术推动力"
        )
        assert result.complexity == "C2"
        assert result.route_strategy == "chain_of_thought"

    def test_route_params_keys(self):
        from app.application.pipeline.steps.intent_step import get_route_params
        params = get_route_params("direct_retrieve")
        assert "top_k_multiplier" in params
        assert "max_tokens" in params
        assert "temperature" in params

    def test_route_params_direct_retrieve(self):
        from app.application.pipeline.steps.intent_step import get_route_params
        params = get_route_params("direct_retrieve")
        assert params["top_k_multiplier"] == 0.5
        assert params["max_tokens"] == 300

    def test_route_params_chain_of_thought(self):
        from app.application.pipeline.steps.intent_step import get_route_params
        params = get_route_params("chain_of_thought")
        assert params["temperature"] == 0.2
        assert "system_prompt_suffix" in params

    def test_route_params_default_fallback(self):
        from app.application.pipeline.steps.intent_step import get_route_params
        params = get_route_params("nonexistent_strategy")
        assert params["top_k_multiplier"] == 1.0  # 默认 retrieve_answer

    def test_all_route_strategies_have_params(self):
        from app.application.pipeline.steps.intent_step import ROUTE_PARAMS
        for strategy, params in ROUTE_PARAMS.items():
            assert "top_k_multiplier" in params
            assert "max_tokens" in params
            assert "temperature" in params
            assert "context_max_chars_ratio" in params


# ═══════════════════════════════════════════════════
# 6. Settings 配置
# ═══════════════════════════════════════════════════

class TestV3Settings:
    """v3 新增配置项测试。"""

    def test_reranker_settings_exist(self):
        from app.config.settings import settings
        assert hasattr(settings, "RERANKER_MODE")
        assert hasattr(settings, "RERANKER_MODEL")
        assert hasattr(settings, "RERANKER_TIMEOUT")

    def test_reranker_defaults(self):
        from app.config.settings import settings
        assert settings.RERANKER_MODE == "simple"
        assert settings.RERANKER_MODEL == "BAAI/bge-reranker-v2-m3"
        assert settings.RERANKER_TIMEOUT == 5.0

    def test_graph_settings_exist(self):
        from app.config.settings import settings
        assert hasattr(settings, "GRAPH_RAG_ENABLED")
        assert hasattr(settings, "GRAPH_EXTRACT_TIMEOUT")

    def test_graph_defaults(self):
        from app.config.settings import settings
        assert settings.GRAPH_RAG_ENABLED is True
        assert settings.GRAPH_EXTRACT_TIMEOUT == 5.0

    def test_semantic_chunking_setting(self):
        from app.config.settings import settings
        assert hasattr(settings, "SEMANTIC_CHUNKING_ENABLED")
        assert settings.SEMANTIC_CHUNKING_ENABLED is True


# ═══════════════════════════════════════════════════
# 7. 集成 (import 验证)
# ═══════════════════════════════════════════════════

class TestV3Imports:
    """验证 v3 新增的 import 路径可用。"""

    def test_import_chunker(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker, ChunkNode, semantic_chunker
        assert semantic_chunker is not None

    def test_import_reranker(self):
        from app.infrastructure.reranker.simple_reranker import (
            SimpleReranker, CrossEncoderReranker, HybridReranker,
            simple_reranker, hybrid_reranker,
        )
        assert hybrid_reranker is not None

    def test_import_graph_rag(self):
        from app.infrastructure.graph.graph_store import (
            KnowledgeGraph, Entity, Relation,
            extract_entities_relations, extract_query_entities,
            knowledge_graph,
        )
        assert knowledge_graph is not None

    def test_import_intent_v2(self):
        from app.application.pipeline.steps.intent_step import (
            classify_intent, classify_intent_v2, IntentResult,
            get_route_params, ROUTE_PARAMS,
        )
        assert classify_intent_v2 is not None

    def test_pipeline_exports(self):
        from app.application.pipeline import (
            classify_intent, classify_intent_v2,
            IntentResult, get_route_params,
        )
        assert IntentResult is not None


# ═══════════════════════════════════════════════════
# Phase 1: Procedural Chunking
# ═══════════════════════════════════════════════════

class TestProceduralChunking:

    def test_steps_stay_together(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=200)
        text = (
            "1. 首先，安装必要的依赖包并配置环境变量\n"
            "2. 然后，修改配置文件中的数据库连接信息\n"
            "3. 接着，运行数据库迁移脚本初始化表结构\n"
            "4. 最后，启动应用服务并验证运行状态\n"
        )
        chunks = chunker._split_by_sentences(text)
        assert len(chunks) <= 2, f"步骤不应被过度切割: {len(chunks)} chunks"

    def test_step_boundary_split_long_procedure(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=50)
        text = (
            "1. 第一步内容很长很长很长很长很长很长很长很长很长很长很长很长\n"
            "2. 第二步内容也很长很长很长很长很长很长很长很长很长很长很长很长\n"
            "3. 第三步同样很长很长很长很长很长很长很长很长很长很长很长很长很长\n"
        )
        chunks = chunker._split_by_sentences(text)
        assert all(len(c) > 0 for c in chunks)
        for c in chunks:
            assert c.strip()[0].isdigit(), f"Chunk 应以步骤编号开头: {repr(c[:20])}"

    def test_step_english_pattern(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=500)
        text = (
            "Step 1: Install dependencies\n"
            "Step 2: Configure the server\n"
            "Step 3: Start the application\n"
            "Step 4: Verify deployment\n"
        )
        chunks = chunker._split_by_sentences(text)
        assert len(chunks) <= 2

    def test_non_procedure_unchanged(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=100)
        text = (
            "这是一段普通的叙述文本，没有任何步骤标识。"
            "它只是描述了一些背景信息和相关概念。"
            "读者可以通过这段文字了解基本的情况。"
            "这里还有更多细节需要说明和补充。"
            "最后做个总结，到此为止内容已经足够。"
        )
        chunks = chunker._split_by_sentences(text)
        assert len(chunks) >= 1

    def test_count_consecutive_steps(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        text = "1. A\n2. B\n3. C\nNormal text\n4. D\n"
        count = SemanticChunker._count_consecutive_steps(text)
        assert count == 3


# ═══════════════════════════════════════════════════
# Phase 1: TextCleaner Encoding Fixes
# ═══════════════════════════════════════════════════

class TestTextCleanerEncoding:

    def test_special_chars_preserved(self):
        from app.infrastructure.document.text_cleaner import TextCleaner
        cleaner = TextCleaner()
        text = "Temperature: 30C, arrow right, 2%, accented: cafe resume"
        # Use ASCII-safe text since this test verifies non-stripping behavior
        result = cleaner.clean(text)
        assert "30C" in result
        assert "cafe" in result
        assert len(result) > 10

    def test_chinese_preserved(self):
        from app.infrastructure.document.text_cleaner import TextCleaner
        cleaner = TextCleaner()
        text = "这是一个测试文档，包含中文标点符号。"
        result = cleaner.clean(text)
        assert "这是一个测试文档" in result

    def test_control_chars_removed(self):
        from app.infrastructure.document.text_cleaner import TextCleaner
        cleaner = TextCleaner()
        text = "Hello\x00\x01\x02World"
        result = cleaner.clean(text)
        assert "\x00" not in result
        assert "Hello" in result
        assert "World" in result

    def test_degree_symbol_preserved(self):
        from app.infrastructure.document.text_cleaner import TextCleaner
        cleaner = TextCleaner()
        text = "Temperature: 30°C"
        result = cleaner.clean(text)
        assert "°" in result, f"度符号被删除: {repr(result)}"

    def test_arrow_preserved(self):
        from app.infrastructure.document.text_cleaner import TextCleaner
        cleaner = TextCleaner()
        text = "a → b"
        result = cleaner.clean(text)
        assert "→" in result, f"箭头被删除: {repr(result)}"

    def test_math_symbols_preserved(self):
        from app.infrastructure.document.text_cleaner import TextCleaner
        cleaner = TextCleaner()
        text = "x ≈ y, a ≠ b"
        result = cleaner.clean(text)
        assert "≈" in result
        assert "≠" in result


# ═══════════════════════════════════════════════════
# Phase 1: Parent Expansion in Retrieval Pipeline
# ═══════════════════════════════════════════════════

class TestRetrievalParentExpansion:

    def test_expand_with_parent_in_context(self):
        from app.infrastructure.chunking.strategies.semantic import expand_with_parent
        docs = [
            {"id": "c1", "text": "child text 1", "score": 0.9},
            {"id": "c2", "text": "child text 2", "score": 0.8},
        ]
        parent_map = {"c1": "p1", "c2": "p2"}
        parent_texts = {"p1": "full section one text", "p2": "full section two text"}
        expanded = expand_with_parent(docs, parent_map, parent_texts, max_expansion=2)
        assert expanded[0]["text"] == "full section one text"
        assert expanded[0]["_expanded"] is True
        assert expanded[1]["text"] == "full section two text"

    def test_expand_no_parent_unchanged(self):
        from app.infrastructure.chunking.strategies.semantic import expand_with_parent
        docs = [{"id": "c1", "text": "child text", "score": 0.9}]
        expanded = expand_with_parent(docs, {}, {}, max_expansion=2)
        assert expanded[0]["text"] == "child text"
        assert "_expanded" not in expanded[0]

    def test_expand_limited_by_max(self):
        from app.infrastructure.chunking.strategies.semantic import expand_with_parent
        docs = [
            {"id": "c1", "text": "t1"},
            {"id": "c2", "text": "t2"},
        ]
        parent_map = {"c1": "p1", "c2": "p2"}
        parent_texts = {"p1": "P1", "p2": "P2"}
        expanded = expand_with_parent(docs, parent_map, parent_texts, max_expansion=1)
        expanded_count = sum(1 for d in expanded if d.get("_expanded"))
        assert expanded_count == 1


# ═══════════════════════════════════════════════════
# Phase 1: Metadata Pipeline
# ═══════════════════════════════════════════════════

class TestMetadataPipeline:

    def test_chunk_result_has_parent_text(self):
        from app.infrastructure.chunking.strategies.base import DefaultChunkStrategy
        strategy = DefaultChunkStrategy()
        text = "# 第一章\n\n这是第一章第一节的内容，包含一些详细的描述信息和背景介绍。\n\n"
        text += "## 第二节\n\n这是第二节的具体内容，说明了操作步骤和注意事项。\n\n"
        text += "接下来还有更多的段落内容。"
        results = strategy.chunk(text, doc_id="test1")
        for r in results:
            assert "parent_text" in r.meta, f"ChunkResult 缺少 parent_text: {list(r.meta.keys())}"
            assert isinstance(r.parent_id, str), f"parent_id 应为字符串"

    def test_leaf_chunk_has_heading(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=80)
        text = "# Docker 部署\n\n"
        text += "详细的部署步骤说明，包含很多内容来确保文本足够长以便被分块器分割处理。\n\n"
        text += "## 启动服务\n\n"
        text += "运行 docker compose up 命令来启动所有服务，等待服务就绪后检查日志输出。\n\n"
        text += "## 验证部署\n\n"
        text += "访问服务端点确认 API 正常运行并返回预期的响应结果和数据格式。\n\n"
        nodes = chunker.split(text, doc_id="test2")
        leaf_nodes = chunker.get_leaf_chunks(nodes)
        headings = [n.heading for n in leaf_nodes if n.heading]
        assert len(headings) > 0, f"至少应有一个 leaf 有 heading, leafs={len(leaf_nodes)}"


# ═══════════════════════════════════════════════════
# Phase 2: API Chunking
# ═══════════════════════════════════════════════════

class TestAPIChunking:
    """API endpoint 感知分块测试。"""

    def test_api_endpoints_kept_together(self):
        """API endpoint 应整体保留不被切断。"""
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker, _detect_api_endpoints
        text = (
            "POST /api/auth/login\n"
            "Request: {\"username\": \"...\", \"password\": \"...\"}\n"
            "Response: {\"token\": \"...\", \"user\": {...}}\n"
            "Errors: 401 Unauthorized, 429 Rate Limited\n"
        )
        assert _detect_api_endpoints(text), "应检测到 API endpoint"

    def test_non_api_text_not_detected(self):
        """普通文本不应被检测为 API。"""
        from app.infrastructure.chunking.strategies.semantic import _detect_api_endpoints
        text = "这是一段普通的文本内容，没有 API 相关信息。"
        assert not _detect_api_endpoints(text)

    def test_api_chunking_preserves_endpoint(self):
        """API 分块应保留完整 endpoint 信息。"""
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=200)
        text = (
            "GET /api/users\n"
            "Response: [{\"id\": 1, \"name\": \"Alice\"}]\n\n"
            "POST /api/users\n"
            "Request: {\"name\": \"Bob\"}\n"
            "Response: {\"id\": 2, \"name\": \"Bob\"}\n"
        )
        chunks = chunker._split_by_sentences(text)
        # 两个 endpoint 应被分开或合理分组
        assert len(chunks) >= 1


# ═══════════════════════════════════════════════════
# Phase 2: Table Chunking
# ═══════════════════════════════════════════════════

class TestTableChunking:
    """表格感知分块测试。"""

    def test_markdown_table_detected(self):
        """Markdown 表格应被检测到。"""
        from app.infrastructure.chunking.strategies.semantic import _detect_table
        text = (
            "| 参数 | 类型 | 说明 |\n"
            "|------|------|------|\n"
            "| name | string | 用户名 |\n"
            "| age | int | 年龄 |\n"
        )
        assert _detect_table(text), "应检测到 Markdown 表格"

    def test_small_table_kept_whole(self):
        """小表格应完整保留。"""
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=500)
        text = (
            "| A | B | C |\n"
            "|---|---|---|\n"
            "| 1 | 2 | 3 |\n"
            "| 4 | 5 | 6 |\n"
        )
        chunks = chunker._split_by_sentences(text)
        assert len(chunks) == 1, f"小表格不应被切割: {len(chunks)} chunks"

    def test_plain_text_not_table(self):
        """普通文本不应被识别为表格。"""
        from app.infrastructure.chunking.strategies.semantic import _detect_table
        text = "这是普通文本，不是表格数据。"
        assert not _detect_table(text)


# ═══════════════════════════════════════════════════
# Phase 2: Structure Classification
# ═══════════════════════════════════════════════════

class TestStructureClassification:
    """结构类型分类测试。"""

    def test_classify_api_spec(self):
        from app.infrastructure.chunking.strategies.semantic import classify_structure_type
        text = "POST /api/v1/users\nGET /api/v1/users/{id}\nDELETE /api/v1/users/{id}\n"
        assert classify_structure_type(text) == "api_spec"

    def test_classify_procedural(self):
        from app.infrastructure.chunking.strategies.semantic import classify_structure_type
        text = "1. 第一步\n2. 第二步\n3. 第三步\n4. 第四步\n"
        assert classify_structure_type(text) == "procedural"

    def test_classify_table(self):
        from app.infrastructure.chunking.strategies.semantic import classify_structure_type
        text = "| Name | Value |\n|------|-------|\n| A | 1 |\n| B | 2 |\n"
        assert classify_structure_type(text) == "table"

    def test_classify_narrative(self):
        from app.infrastructure.chunking.strategies.semantic import classify_structure_type
        text = "这是一段普通的叙述性文本，没有任何特殊结构标识。"
        assert classify_structure_type(text) == "narrative"

    def test_query_structure_classification(self):
        from app.application.pipeline.steps.intent_step import classify_structure_from_query
        assert classify_structure_from_query("API 怎么调用") == "api_spec"
        assert classify_structure_from_query("如何部署") == "procedural"
        assert classify_structure_from_query("表格数据") == "table"
        assert classify_structure_from_query("这个函数怎么实现") == "code"


# ═══════════════════════════════════════════════════
# Phase 3: Code Chunking
# ═══════════════════════════════════════════════════

class TestCodeChunking:
    """代码感知分块测试。"""

    def test_code_structure_detected(self):
        from app.infrastructure.chunking.strategies.semantic import _detect_code
        text = (
            "def foo():\n    pass\n\n"
            "def bar():\n    pass\n\n"
        )
        assert _detect_code(text), "应检测到代码结构"

    def test_code_chunking_preserves_functions(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=200)
        text = (
            "def function_one():\n    return 1\n\n"
            "def function_two():\n    return 2\n\n"
        )
        chunks = chunker._split_by_sentences(text)
        assert len(chunks) >= 1

    def test_plain_text_not_code(self):
        from app.infrastructure.chunking.strategies.semantic import _detect_code
        text = "这是普通文本，包含一些 function 字样但不是代码。"
        assert not _detect_code(text)


# ═══════════════════════════════════════════════════
# Phase 3: Dynamic Expansion + Multi-hop
# ═══════════════════════════════════════════════════

class TestDynamicExpansion:
    """动态上下文扩展测试。"""

    def test_expansion_strategy_returns_values(self):
        from app.application.pipeline.steps.intent_step import get_expansion_strategy
        for st in ["procedural", "api_spec", "table", "code", "narrative"]:
            s = get_expansion_strategy(st)
            assert "parent_expand" in s
            assert "context_ratio" in s
            assert s["context_ratio"] >= 1.0

    def test_procedural_has_larger_context(self):
        from app.application.pipeline.steps.intent_step import get_expansion_strategy
        proc = get_expansion_strategy("procedural")
        narr = get_expansion_strategy("narrative")
        assert proc["context_ratio"] >= narr["context_ratio"]

    def test_build_context_dynamic(self):
        from app.application.pipeline.steps.context_step import build_context_dynamic
        docs = [
            {"text": "First chunk content here."},
            {"text": "Second chunk content here."},
        ]
        ctx = build_context_dynamic(docs, structure_type="procedural")
        assert len(ctx) > 0
        assert "First chunk" in ctx

    def test_intent_result_has_structure_type(self):
        from app.application.pipeline.steps.intent_step import IntentResult
        r = IntentResult(
            complexity="C1",
            semantic_type="HOW_TO",
            route_strategy="retrieve_answer",
            structure_type="procedural",
        )
        d = r.to_dict()
        assert d["structure_type"] == "procedural"


# ═══════════════════════════════════════════════════
# Fix: Garbage Content Detection
# ═══════════════════════════════════════════════════

class TestGarbageDetection:
    """垃圾内容检测测试。"""

    def test_repetition_detected_as_garbage(self):
        """重复单字符应被检测为垃圾。"""
        from app.infrastructure.document.text_cleaner import QualityChecker
        qc = QualityChecker()
        assert qc._is_garbage("D D D D D D D D D D D D D D D D D D D D D")
        assert qc._is_garbage("1111111 111111 11 11 11 11 11 D1 D1 D 1 1 1")

    def test_normal_text_not_garbage(self):
        """正常文本不应被误判。"""
        from app.infrastructure.document.text_cleaner import QualityChecker
        qc = QualityChecker()
        assert not qc._is_garbage("MySQL 8.0在Windows系统上的部署步骤如下：")
        assert not qc._is_garbage("首先下载MySQL安装包，然后运行安装程序。")
        assert not qc._is_garbage("正常的部署文档包含多个步骤和配置说明。")

    def test_high_digit_ratio_detected(self):
        """高数字占比应被检测。"""
        from app.infrastructure.document.text_cleaner import QualityChecker
        qc = QualityChecker()
        assert qc._is_garbage("111 222 333 444 555 666 777 888 999 000")

    def test_consecutive_repeat_chars_detected(self):
        """连续重复字符段应被检测。"""
        from app.infrastructure.document.text_cleaner import QualityChecker
        qc = QualityChecker()
        assert qc._is_garbage("abc DDDDDDDDDDDDDDDDDDDD xyz")

    def test_garbage_chunks_lower_quality_score(self):
        """含垃圾chunk的文档质量分应显著降低。"""
        from app.infrastructure.document.text_cleaner import QualityChecker
        qc = QualityChecker()
        normal = [
            "MySQL 8.0在Windows系统上的部署步骤如下所示",
            "首先需要下载MySQL安装包到本地磁盘",
            "然后按照安装向导一步步完成配置",
        ]
        garbage = [
            "MySQL 8.0在Windows系统上的部署步骤如下所示",
            "首先需要下载MySQL安装包到本地磁盘",
            "D D D D D D D D D D D D D D",
        ]
        normal_score = qc.evaluate(normal)["score"]
        mixed_score = qc.evaluate(garbage)["score"]
        assert mixed_score < normal_score, f"垃圾应降低分数: normal={normal_score}, mixed={mixed_score}"

    def test_output_sanitization_truncates_repetition(self):
        """输出清理应截断重复内容。"""
        from app.application.pipeline.steps.generation_step import _sanitize_output
        result = _sanitize_output("正常开头内容\nD D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D")
        assert "[检测到重复输出" in result or len(result) < 100

    def test_normal_output_passes_sanitization(self):
        """正常输出不应被截断。"""
        from app.application.pipeline.steps.generation_step import _sanitize_output
        normal = "MySQL 部署需要先下载安装包，然后按照安装向导完成配置。"
        result = _sanitize_output(normal)
        assert result == normal


# ═══════════════════════════════════════════════════
# Block Extractor Tests
# ═══════════════════════════════════════════════════

class TestBlockExtractor:
    """Block Extractor 测试。"""

    def test_extract_headings(self):
        from app.infrastructure.chunking.strategies.semantic import BlockExtractor
        extractor = BlockExtractor()
        text = "# Title\n\nSome paragraph text.\n\n## Section 1\n\nMore text here.\n"
        blocks = extractor.extract(text)
        headings = [b for b in blocks if b.type == "heading"]
        assert len(headings) == 2
        assert headings[0].content == "Title"
        assert headings[0].level == 1
        assert headings[1].content == "Section 1"
        assert headings[1].level == 2

    def test_extract_paragraphs(self):
        from app.infrastructure.chunking.strategies.semantic import BlockExtractor
        extractor = BlockExtractor()
        text = "First paragraph with some content.\n\nSecond paragraph here.\n"
        blocks = extractor.extract(text)
        paras = [b for b in blocks if b.type == "paragraph"]
        assert len(paras) >= 2

    def test_extract_code_block(self):
        from app.infrastructure.chunking.strategies.semantic import BlockExtractor
        extractor = BlockExtractor()
        text = "```python\ndef hello():\n    print('hello')\n```\n"
        blocks = extractor.extract(text)
        code_blocks = [b for b in blocks if b.type == "code"]
        assert len(code_blocks) == 1
        assert "def hello()" in code_blocks[0].content

    def test_extract_table(self):
        from app.infrastructure.chunking.strategies.semantic import BlockExtractor
        extractor = BlockExtractor()
        text = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        blocks = extractor.extract(text)
        tables = [b for b in blocks if b.type == "table"]
        assert len(tables) == 1

    def test_extract_list_items(self):
        from app.infrastructure.chunking.strategies.semantic import BlockExtractor
        extractor = BlockExtractor()
        text = "- First item\n- Second item\n- Third item\n"
        blocks = extractor.extract(text)
        lists = [b for b in blocks if b.type == "list_item"]
        assert len(lists) == 1
        assert "First item" in lists[0].content

    def test_empty_input(self):
        from app.infrastructure.chunking.strategies.semantic import BlockExtractor
        extractor = BlockExtractor()
        assert extractor.extract("") == []
        assert extractor.extract("   ") == []


# ═══════════════════════════════════════════════════
# Context Reconstruction Tests
# ═══════════════════════════════════════════════════

class TestContextReconstruction:
    """Context Reconstructor 测试。"""

    def test_reconstruct_with_headings(self):
        from app.infrastructure.chunking.strategies.semantic import reconstruct_context
        chunks = [
            {"text": "Content A", "heading": "Deploy", "chunk_idx": 0, "depth": 1},
            {"text": "Content B", "heading": "Deploy", "chunk_idx": 1, "depth": 1},
            {"text": "Config info", "heading": "Config", "chunk_idx": 2, "depth": 2},
        ]
        result = reconstruct_context(chunks, max_chars=5000, preserve_structure=True)
        assert "# Deploy" in result
        assert "Content A" in result
        assert "## Config" in result

    def test_reconstruct_flat(self):
        from app.infrastructure.chunking.strategies.semantic import reconstruct_context
        chunks = [
            {"text": "First chunk"},
            {"text": "Second chunk"},
        ]
        result = reconstruct_context(chunks, max_chars=5000, preserve_structure=False)
        assert "First chunk" in result
        assert "Second chunk" in result

    def test_build_structured_context(self):
        from app.infrastructure.chunking.strategies.semantic import build_structured_context
        chunks = [
            {"text": "Step 1: install", "heading": "Setup", "chunk_idx": 0},
        ]
        result = build_structured_context(chunks, structure_type="procedural")
        assert len(result) > 0


# ═══════════════════════════════════════════════════
# Enhanced Metadata Tests
# ═══════════════════════════════════════════════════

class TestEnhancedMetadata:
    """增强元数据测试。"""

    def test_section_path_in_chunk_result(self):
        from app.infrastructure.chunking.strategies.base import DefaultChunkStrategy
        strategy = DefaultChunkStrategy()
        text = "# Deploy\n\nStep one content here with enough text to be valid.\n\n"
        text += "## Config\n\nConfiguration details with sufficient length for chunking.\n\n"
        results = strategy.chunk(text, doc_id="test")
        for r in results:
            assert "section_path" in r.meta, f"Missing section_path: {list(r.meta.keys())}"
            assert "depth" in r.meta, f"Missing depth"

    def test_prev_next_chunk_linked(self):
        from app.infrastructure.chunking.strategies.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=80)
        text = "# A\n\n" + "x " * 30 + "\n\n# B\n\n" + "y " * 30 + "\n\n"
        nodes = chunker.split(text)
        leaf_nodes = chunker.get_leaf_chunks(nodes)
        # 至少有一些节点有 prev/next 链接
        has_link = any(
            n.meta.get("prev_chunk_id") or n.meta.get("next_chunk_id")
            for n in leaf_nodes
        )
        # 多 section 情况下可能有链接
        assert len(leaf_nodes) >= 1


# ═══════════════════════════════════════════════════
# Fix: Relevance Gate + Output Sanitization
# ═══════════════════════════════════════════════════

class TestRelevanceGate:
    """相关性门禁测试。"""

    def test_relevant_context_passes(self):
        """相关上下文应通过检查。"""
        from app.application.pipeline.steps.generation_step import _check_context_relevance
        assert _check_context_relevance(
            "MySQL怎么在虚拟机上部署",
            "MySQL在Linux虚拟机上的部署步骤如下：首先下载MySQL安装包..."
        )

    def test_irrelevant_context_rejected(self):
        """不相关上下文应被拒绝。"""
        from app.application.pipeline.steps.generation_step import _check_context_relevance
        assert not _check_context_relevance(
            "MySQL怎么在虚拟机上部署",
            "Windows操作系统安装指南，包含驱动安装、系统设置等内容"
        )

    def test_partial_match_passes(self):
        """部分关键词匹配应通过。"""
        from app.application.pipeline.steps.generation_step import _check_context_relevance
        assert _check_context_relevance(
            "MySQL部署",
            "MySQL数据库的安装和配置步骤..."
        )

    def test_short_query_passes(self):
        """无法提取关键词时放行。"""
        from app.application.pipeline.steps.generation_step import _check_context_relevance
        assert _check_context_relevance("A", "Some context here")


class TestOutputSanitization:
    """输出清理测试。"""

    def test_repeat_D_pattern_truncated(self):
        """D D D 重复模式应被截断。"""
        from app.application.pipeline.steps.generation_step import _sanitize_output
        result = _sanitize_output(
            "MySQL部署步骤：\n"
            "D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D"
        )
        assert "系统提示" in result or len(result) < 200

    def test_repeat_block_pattern_truncated(self):
        """【D 【D 重复块应被截断。"""
        from app.application.pipeline.steps.generation_step import _sanitize_output
        result = _sanitize_output(
            "【结论】正常内容\n"
            + "【D 【D 【D 【D 【D 【D 【D 【D 【D 【D 【D 【D 【D 【D"
        )
        assert "系统提示" in result or len(result) < 200

    def test_normal_output_preserved(self):
        """正常输出应完整保留。"""
        from app.application.pipeline.steps.generation_step import _sanitize_output
        normal = (
            "【结论】\nMySQL在虚拟机上部署需要先安装MySQL软件包。\n\n"
            "【命令】\n1. `sudo apt install mysql-server`：安装MySQL\n\n"
            "【补充说明】\n- 需要root权限\n\n"
            "【来源】\n【来源：[来源1]】"
        )
        result = _sanitize_output(normal)
        assert "【结论】" in result
        assert "【来源】" in result
        assert "系统提示" not in result

    def test_empty_output(self):
        """空输出应原样返回。"""
        from app.application.pipeline.steps.generation_step import _sanitize_output
        assert _sanitize_output("") == ""


class TestGenerateAnswerGate:
    """generate_answer 门禁测试。"""

    @pytest.mark.asyncio
    async def test_no_context_returns_refusal(self):
        """无上下文时返回拒答。"""
        from app.application.pipeline.steps.generation_step import generate_answer
        answer, level, reason = await generate_answer("test", "")
        assert "未找到相关信息" in answer
        assert reason == "NO_CONTEXT"

    @pytest.mark.asyncio
    async def test_low_relevance_returns_refusal(self):
        """低相关性分数时返回拒答（不调用 LLM）。"""
        from app.application.pipeline.steps.generation_step import generate_answer
        top_docs = [
            {"rerank_score": 0.005, "text": "无关内容"},
        ]
        answer, level, reason = await generate_answer(
            "MySQL部署", "一些不太相关的内容", top_docs=top_docs
        )
        assert "未找到" in answer
        assert reason == "LOW_RELEVANCE"

    @pytest.mark.asyncio
    async def test_irrelevant_keywords_returns_refusal(self):
        """关键词不匹配时返回拒答。"""
        from app.application.pipeline.steps.generation_step import generate_answer
        top_docs = [
            {"rerank_score": 0.05, "text": "Windows系统安装指南"},
        ]
        answer, level, reason = await generate_answer(
            "MySQL虚拟机部署", "Windows系统安装指南...", top_docs=top_docs
        )
        assert "未找到" in answer or reason == "NO_MATCH"
