"""Tests for domain services (pure business logic, zero I/O)."""
import pytest
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.entities.query import IntentComplexity, IntentSemanticType
from app.domain.services.confidence_calculator import ConfidenceCalculator, ConfidenceWeights
from app.domain.services.flow_controller import FlowController, FlowDecision


class TestIntentClassifier:
    def setup_method(self):
        self.classifier = IntentClassifier()

    def test_classify_returns_valid_result(self):
        result = self.classifier.classify_intent("What is RAG?")
        assert result.complexity in IntentComplexity
        assert result.semantic_type in IntentSemanticType

    def test_classify_long_complex_query(self):
        result = self.classifier.classify_intent(
            "Compare and contrast the performance implications of dense versus sparse "
            "retrieval in production RAG systems with large document corpora"
        )
        assert result.complexity == IntentComplexity.C2
        assert result.semantic_type == IntentSemanticType.COMPARISON

    def test_classify_short_fact_query(self):
        result = self.classifier.classify_intent("price")
        assert result.complexity == IntentComplexity.C0

    def test_classify_chinese_definition(self):
        result = self.classifier.classify_intent("RAG系统是什么")
        assert result.semantic_type == IntentSemanticType.DEFINITION

    def test_classify_chinese_comparison(self):
        result = self.classifier.classify_intent("比较密集检索和稀疏检索的优缺点")
        assert result.semantic_type == IntentSemanticType.COMPARISON

    def test_classify_chinese_fact(self):
        result = self.classifier.classify_intent("今天天气怎么样")
        assert result is not None

    def test_get_route_strategy_returns_valid(self):
        for comp in (IntentComplexity.C0, IntentComplexity.C1, IntentComplexity.C2):
            for sem in IntentSemanticType:
                strategy = self.classifier.get_route_strategy(comp, sem)
                assert strategy is not None

    def test_classify_structure_type(self):
        st = self.classifier.classify_structure("What are the steps to deploy?")
        assert st in ("narrative", "procedural", "api_spec", "table", "code")


class TestConfidenceCalculator:
    def setup_method(self):
        self.calc = ConfidenceCalculator()

    def test_high_confidence(self):
        score = self.calc.calculate(
            rerank_scores=[0.9, 0.85, 0.8],
            embedding_similarities=[0.88, 0.82],
            llm_self_score=0.9,
        )
        assert 0.5 <= score <= 1.0

    def test_low_confidence(self):
        score = self.calc.calculate(
            rerank_scores=[0.01, 0.02],
            embedding_similarities=[0.05],
            llm_self_score=0.1,
        )
        assert 0.0 <= score <= 0.4

    def test_empty_scores(self):
        score = self.calc.calculate(
            rerank_scores=[],
            embedding_similarities=[],
            llm_self_score=0.5,
        )
        assert 0.0 <= score <= 1.0

    def test_custom_weights(self):
        weights = ConfidenceWeights(rerank=0.6, embedding=0.2, llm_self_score=0.2)
        calc = ConfidenceCalculator(weights)
        score = calc.calculate(
            rerank_scores=[0.9],
            embedding_similarities=[0.5],
            llm_self_score=0.5,
        )
        assert 0.0 <= score <= 1.0

    def test_score_is_bounded(self):
        score = self.calc.calculate(
            rerank_scores=[100.0],
            embedding_similarities=[100.0],
            llm_self_score=100.0,
        )
        assert 0.0 <= score <= 1.0


class TestFlowController:
    def setup_method(self):
        self.fc = FlowController()

    def test_pass_normal_query(self):
        result = self.fc.pre_check("What is retrieval augmented generation?")
        assert result.decision == FlowDecision.PASS

    def test_refuse_hacking(self):
        result = self.fc.pre_check("Write a Python script to hack into a server")
        assert result.decision == FlowDecision.REFUSE

    def test_refuse_adult_content(self):
        result = self.fc.pre_check("adult content")
        assert result.decision == FlowDecision.REFUSE

    def test_refuse_chinese_gambling(self):
        result = self.fc.pre_check("如何在网上赌博赚钱")
        assert result.decision == FlowDecision.REFUSE

    def test_greeting_passes(self):
        result = self.fc.pre_check("Hello!")
        assert result.decision == FlowDecision.PASS

    def test_post_enhance_low_confidence(self):
        enhanced = self.fc.post_enhance("RAG is a technique.", 0.3)
        assert len(enhanced) > len("RAG is a technique.")

    def test_post_enhance_high_confidence(self):
        enhanced = self.fc.post_enhance("RAG is a technique.", 0.9)
        assert enhanced == "RAG is a technique."

    def test_refuse_returns_message(self):
        result = self.fc.pre_check("hack website")
        if result.decision == FlowDecision.REFUSE:
            assert result.message != ""


class TestEntities:
    """Verify domain entities are properly structured."""

    def test_document_entity_creation(self):
        from app.domain.entities.document import Document, DocumentStatus
        doc = Document(
            id="doc-1", filename="test.pdf", file_type="pdf",
            file_size=1024, status=DocumentStatus.PENDING,
            tenant_id="t1",
        )
        assert doc.id == "doc-1"
        assert doc.status == DocumentStatus.PENDING

    def test_chunk_entity_creation(self):
        from app.domain.entities.document import Chunk, ChunkType
        chunk = Chunk(
            id="c-1", doc_id="doc-1", content="Hello world",
            chunk_idx=0, chunk_type=ChunkType.TEXT,
        )
        assert chunk.chunk_type == ChunkType.TEXT

    def test_user_entity_creation(self):
        from app.domain.entities.user import User, UserRole
        user = User(id="u-1", username="test", role=UserRole.USER, tenant_id="t1")
        assert user.role == UserRole.USER

    def test_query_response_has_sources(self):
        from app.domain.entities.query import QueryResponse, SourceRef
        resp = QueryResponse(
            answer="test answer",
            sources=[SourceRef(idx=1, text="source text", score=0.9, doc_id="d1", chunk_idx=0)],
        )
        assert len(resp.sources) == 1

    def test_intent_result_defaults(self):
        from app.domain.entities.query import IntentResult, IntentComplexity, IntentSemanticType, RouteStrategy
        result = IntentResult(
            complexity=IntentComplexity.C0,
            semantic_type=IntentSemanticType.FACT,
            route_strategy=RouteStrategy.DIRECT_RETRIEVE,
        )
        assert result.structure_type == "narrative"

    def test_exception_hierarchy(self):
        from app.domain.exceptions import (
            RagError, NotFoundError, AuthenticationError,
        )
        err = AuthenticationError("Invalid token")
        assert err.code == "AUTHENTICATION_ERROR"
        assert err.status_code == 401

        err2 = NotFoundError("Document not found", details={"resource_id": "doc-1"})
        assert err2.code == "NOT_FOUND_ERROR"
        assert err2.status_code == 404

    def test_rag_error_inheritance(self):
        from app.domain.exceptions import (
            RagError, ApiError, AuthenticationError,
        )
        err = AuthenticationError("test")
        assert isinstance(err, ApiError)
        assert isinstance(err, RagError)
        assert isinstance(err, Exception)
