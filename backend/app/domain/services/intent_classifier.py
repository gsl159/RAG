"""Pure rule-based intent, complexity, and structure classification for RAG routing.

No LLM calls, no I/O. All decisions are made via keyword matching and
heuristic rules, making this layer fast and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IntentComplexity(StrEnum):
    """Query complexity tier used to select LLM model and timeout."""

    C0 = "C0"  # Simple: answer directly, no retrieval needed
    C1 = "C1"  # Moderate: single-turn retrieval + generation
    C2 = "C2"  # Complex: multi-step reasoning, tool calls, agent loop


class IntentSemanticType(StrEnum):
    """Semantic intent of the user query."""

    FACT = "FACT"
    COMPARISON = "COMPARISON"
    REASONING = "REASONING"
    ACTION = "ACTION"
    OPINION = "OPINION"
    DEFINITION = "DEFINITION"
    ANALYSIS = "ANALYSIS"
    SUMMARY = "SUMMARY"
    LIST = "LIST"
    GREETING = "GREETING"
    CLARIFICATION = "CLARIFICATION"
    UNKNOWN = "UNKNOWN"


class RouteStrategy(StrEnum):
    """Routing strategy determined by (complexity, semantic_type)."""

    DIRECT_ANSWER = "direct_answer"
    RETRIEVE_ONLY = "retrieve_only"
    RAG = "rag"                       # Retrieve + generate
    AGENTIC_RAG = "agentic_rag"       # Multi-step agent with tool calls
    TOOL_CALL = "tool_call"           # External tool execution
    MULTI_STEP = "multi_step"         # Decompose and execute sub-queries
    CLARIFY = "clarify"               # Ask user for more details
    REFUSE = "refuse"                 # Block the query


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntentResult:
    """The complete classification output for a single query.

    Attributes:
        query: The original query string.
        complexity: The complexity tier (C0 / C1 / C2).
        semantic_type: The dominant semantic intent.
        structure_type: The expected answer structure (narrative, procedural,
            code, table, api_spec, or unknown).
        route_strategy: The routing decision derived from the above.
        confidence: How confident the classifier is in the result (0.0-1.0).
    """

    query: str
    complexity: IntentComplexity = IntentComplexity.C1
    semantic_type: IntentSemanticType = IntentSemanticType.UNKNOWN
    structure_type: str = "unknown"
    route_strategy: RouteStrategy = RouteStrategy.RAG
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Keyword patterns (Chinese-first)
# ---------------------------------------------------------------------------

INTENT_PATTERNS: dict[IntentSemanticType, list[str]] = {
    IntentSemanticType.FACT: [
        # Chinese
        "是什么", "什么是", "有哪些", "有哪", "何时", "何地", "谁",
        "多少", "哪个", "哪里", "怎么来的", "定义", "概念",
        "解释一下", "介绍一下", "说明", "描述", "列举", "列出",
        "告诉我", "查询", "查一下", "查找", "搜索", "找出",
        "请教", "请问", "想问", "想了解",
        # English
        "what is", "what are", "when did", "where is", "who is",
        "how many", "how much", "which", "define", "definition",
        "tell me about", "explain", "list", "find", "search for",
        "describe", "facts about", "information about",
    ],
    IntentSemanticType.COMPARISON: [
        # Chinese
        "对比", "比较", "区别", "差异", "不同", "优劣", "优缺点",
        "哪个好", "哪个更", "哪个适合", "vs", "versus",
        "与...相比", "相比之", "有什么不同", "差别", "异同",
        "哪个更优", "哪个更好", "如何选择", "怎么选",
        # English
        "compare", "comparison", "difference", "versus", "vs",
        "pros and cons", "advantages and disadvantages",
        "better than", "worse than", "similarities",
        "which is better", "how does * differ", "differentiate",
    ],
    IntentSemanticType.REASONING: [
        # Chinese
        "为什么", "为何", "原因", "理由", "原理", "根源",
        "如何导致", "会造成", "如何影响", "影响", "后果",
        "因果关系", "推导", "推理", "论证", "解释原因",
        "为什么这样", "原因是什么", "背后原因",
        # English
        "why", "reason", "cause", "because", "how does",
        "what causes", "what is the reason", "explain why",
        "rationale", "root cause", "lead to", "result in",
        "effect of", "impact on", "relationship between",
    ],
    IntentSemanticType.ACTION: [
        # Chinese
        "怎么做", "如何做", "怎样", "步骤", "方法", "方式",
        "如何实现", "如何操作", "操作步骤", "操作流程",
        "教程", "指南", "指导", "入门", "实践",
        "怎么使用", "如何使用", "用法", "配置", "设置",
        "搭建", "部署", "安装", "创建", "生成",
        "代码示例", "示例", "例子",
        # English
        "how to", "how do i", "steps to", "tutorial", "guide",
        "instructions", "walkthrough", "setup", "configure",
        "install", "deploy", "create", "generate", "build",
        "example", "code example", "sample code",
        "implementation", "how can i", "way to",
    ],
    IntentSemanticType.OPINION: [
        # Chinese
        "看法", "观点", "评价", "评论", "你觉得", "你认为",
        "推荐", "建议", "意见", "怎么看", "如何看待",
        "哪个好", "好不好用", "值得", "推荐吗",
        "体验", "感受", "口碑",
        # English
        "opinion", "review", "thoughts on", "what do you think",
        "recommend", "suggestion", "advice", "feedback",
        "rating", "how do you like", "impressions",
    ],
    IntentSemanticType.DEFINITION: [
        # Chinese
        "定义", "意思是", "含义", "指的是", "是指",
        "什么是", "何为", "何谓", "解释", "释义",
        "是什么", "定义是",
        # English
        "definition", "meaning", "define", "what does * mean",
        "what is the definition", "term", "concept",
        "stands for", "abbreviation", "acronym",
    ],
    IntentSemanticType.ANALYSIS: [
        # Chinese
        "分析", "剖析", "评估", "评价", "衡量",
        "综述", "总结分析", "深度分析", "分析报告",
        "优劣势", "竞争力", "市场分析", "趋势",
        "预测", "展望",
        # English
        "analysis", "analyze", "assessment", "evaluation",
        "review", "overview", "deep dive", "trend",
        "forecast", "predict", "SWOT", "strengths and weaknesses",
    ],
    IntentSemanticType.SUMMARY: [
        # Chinese
        "总结", "概括", "归纳", "摘要", "概要", "简述",
        "简要说明", "提炼", "核心", "要点",
        "主要", "关键点", "重点",
        # English
        "summarize", "summary", "sum up", "overview",
        "brief", "key points", "main points", "highlights",
        "recap", "tl;dr", "tldr",
    ],
    IntentSemanticType.LIST: [
        # Chinese
        "列表", "清单", "目录", "有哪些", "列举",
        "列出", "所有", "全部", "各项", "每个",
        # English
        "list", "items", "catalog", "directory",
        "all", "every", "each", "enumeration",
        "top *", "best *",
    ],
    IntentSemanticType.GREETING: [
        # Chinese
        "你好", "您好", "嗨", "哈喽", "hello", "hi",
        "早上好", "下午好", "晚上好", "你好吗",
        "在吗", "在不在", "hey", "good morning",
        "good afternoon", "good evening", "嗨喽",
        # English
        "hello", "hi", "hey", "good morning", "good afternoon",
        "good evening", "how are you", "howdy", "greetings",
    ],
    IntentSemanticType.CLARIFICATION: [
        # Chinese
        "什么意思", "没明白", "不懂", "再说一遍",
        "能详细点吗", "举个例子", "比如",
        "能再说一下吗", "没听懂",
        # English
        "what do you mean", "i don't understand",
        "can you explain", "for example", "e.g.",
        "could you elaborate", "clarify", "more details",
        "can you repeat",
    ],
}

# ---------------------------------------------------------------------------
# Complexity rules
# ---------------------------------------------------------------------------

# Short queries that can be answered directly without retrieval
C0_PATTERNS: list[str] = [
    # Simple greetings
    "你好", "您好", "嗨", "hello", "hi", "hey",
    "在吗", "早上好", "下午好", "晚上好",
    # Simple confirmations
    "好的", "是的", "对的", "不是", "不对", "yes", "no", "ok",
    "谢谢", "感谢", "thanks", "thank you",
    "再见", "拜拜", "bye", "goodbye",
    # Simple follow-ups
    "然后呢", "还有呢", "继续", "接着说",
    "为什么", "why", "然后", "so",
    "嗯", "哦", "好",
]

# Keywords that indicate C1 complexity even if query is short
C1_KEYWORDS: list[str] = [
    # Chinese
    "是", "叫", "有", "可以", "能", "会",
    "做", "用", "在", "到", "给", "对",
    # English
    "is", "are", "can", "does", "have", "has",
    "do", "make", "use", "get",
]

# Keywords that indicate C2 complexity
C2_KEYWORDS: list[str] = [
    # Chinese
    "对比分析", "综合分析", "详细说明", "深入研究",
    "比较", "优劣", "差异分析", "多维度",
    "复述", "改写", "翻译成", "总结",
    "对比", "区别", "关系", "影响",
    "代码", "代码示例", "程序", "函数", "算法",
    "实现", "实现方式", "架构", "设计模式",
    # English
    "compare and contrast", "comprehensive analysis",
    "detailed explanation", "in-depth", "multi-step",
    "code", "function", "algorithm", "implementation",
    "architecture", "design pattern", "translate",
    "rewrite", "paraphrase", "summarize",
]

# ---------------------------------------------------------------------------
# Structure keywords
# ---------------------------------------------------------------------------

STRUCTURE_KEYWORDS: dict[str, list[str]] = {
    "procedural": [
        # Chinese
        "步骤", "流程", "方法", "操作", "教程", "指南",
        "如何", "怎么做", "怎样",
        # English
        "steps", "procedure", "how to", "guide", "tutorial",
        "walkthrough", "instructions",
    ],
    "api_spec": [
        # Chinese
        "api", "接口", "调用", "请求", "响应",
        "端点", "参数", "返回值",
        # English
        "api", "endpoint", "rest", "graphql", "request",
        "response", "parameter", "return value",
    ],
    "table": [
        # Chinese
        "表格", "表", "列表", "汇总", "对比表",
        "一览表", "清单",
        # English
        "table", "list", "chart", "matrix", "spreadsheet",
        "comparison table",
    ],
    "code": [
        # Chinese
        "代码", "代码示例", "示例代码", "函数", "编程",
        "程序", "脚本", "实现", "源码",
        # English
        "code", "code example", "snippet", "function",
        "program", "script", "source code", "implementation",
    ],
    "narrative": [
        # Chinese
        "解释", "说明", "描述", "介绍", "阐述",
        "讨论", "论述", "分析",
        # English
        "explain", "describe", "discuss", "elaborate",
        "narrative", "paragraph",
    ],
}

# ---------------------------------------------------------------------------
# Route mapping: (complexity, semantic_type) -> RouteStrategy
# ---------------------------------------------------------------------------

ROUTE_MAPPING: dict[tuple[IntentComplexity, IntentSemanticType], RouteStrategy] = {
    # C0: simple queries answered directly
    (IntentComplexity.C0, IntentSemanticType.GREETING): RouteStrategy.DIRECT_ANSWER,
    (IntentComplexity.C0, IntentSemanticType.CLARIFICATION): RouteStrategy.DIRECT_ANSWER,
    (IntentComplexity.C0, IntentSemanticType.FACT): RouteStrategy.DIRECT_ANSWER,
    (IntentComplexity.C0, IntentSemanticType.UNKNOWN): RouteStrategy.DIRECT_ANSWER,
    # C1: standard retrieval-augmented generation
    (IntentComplexity.C1, IntentSemanticType.FACT): RouteStrategy.RAG,
    (IntentComplexity.C1, IntentSemanticType.DEFINITION): RouteStrategy.RAG,
    (IntentComplexity.C1, IntentSemanticType.SUMMARY): RouteStrategy.RAG,
    (IntentComplexity.C1, IntentSemanticType.LIST): RouteStrategy.RAG,
    (IntentComplexity.C1, IntentSemanticType.OPINION): RouteStrategy.RAG,
    (IntentComplexity.C1, IntentSemanticType.CLARIFICATION): RouteStrategy.CLARIFY,
    (IntentComplexity.C1, IntentSemanticType.GREETING): RouteStrategy.DIRECT_ANSWER,
    (IntentComplexity.C1, IntentSemanticType.ACTION): RouteStrategy.RAG,
    (IntentComplexity.C1, IntentSemanticType.ANALYSIS): RouteStrategy.RAG,
    # C2: complex tasks requiring multi-step or agentic processing
    (IntentComplexity.C2, IntentSemanticType.COMPARISON): RouteStrategy.AGENTIC_RAG,
    (IntentComplexity.C2, IntentSemanticType.REASONING): RouteStrategy.AGENTIC_RAG,
    (IntentComplexity.C2, IntentSemanticType.ANALYSIS): RouteStrategy.AGENTIC_RAG,
    (IntentComplexity.C2, IntentSemanticType.ACTION): RouteStrategy.MULTI_STEP,
    (IntentComplexity.C2, IntentSemanticType.FACT): RouteStrategy.MULTI_STEP,
    (IntentComplexity.C2, IntentSemanticType.SUMMARY): RouteStrategy.MULTI_STEP,
    (IntentComplexity.C2, IntentSemanticType.CLARIFICATION): RouteStrategy.CLARIFY,
    (IntentComplexity.C2, IntentSemanticType.UNKNOWN): RouteStrategy.CLARIFY,
    # C2 with tool-oriented types
    (IntentComplexity.C2, IntentSemanticType.DEFINITION): RouteStrategy.AGENTIC_RAG,
    (IntentComplexity.C2, IntentSemanticType.LIST): RouteStrategy.AGENTIC_RAG,
    (IntentComplexity.C2, IntentSemanticType.OPINION): RouteStrategy.AGENTIC_RAG,
}


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class IntentClassifier:
    """Pure rule-based classifier that never makes I/O or LLM calls.

    Classifies queries by:
    - Complexity (C0 / C1 / C2)
    - Semantic type (FACT / COMPARISON / REASONING / ...)
    - Expected answer structure (narrative / code / table / ...)
    - Route strategy derived from the above
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_intent(self, query: str) -> IntentResult:
        """Fully classify a query: complexity + semantic + structure + route.

        Args:
            query: The raw user query string.

        Returns:
            An IntentResult with all classification fields populated.
        """
        complexity = self.classify_complexity(query)
        semantic_type = self.classify_semantic(query)
        structure_type = self.classify_structure(query)
        route_strategy = self.get_route_strategy(complexity, semantic_type)
        confidence = self._calculate_confidence(query, semantic_type)

        return IntentResult(
            query=query,
            complexity=complexity,
            semantic_type=semantic_type,
            structure_type=structure_type,
            route_strategy=route_strategy,
            confidence=confidence,
        )

    def classify_complexity(self, query: str) -> IntentComplexity:
        """Determine query complexity tier by heuristic rules.

        Rules:
        - C0: query length < 15 chars AND matches C0_PATTERNS or contains
          only very simple tokens.
        - C1: query < 40 chars OR contains C1_KEYWORDS, no C2 keywords.
        - C2: query >= 40 chars OR contains C2_KEYWORDS.

        Args:
            query: The user query string.

        Returns:
            IntentComplexity.C0, C1, or C2.
        """
        q = query.strip()
        q_lower = q.lower()
        q_len = len(q)

        # C0: very short greetings, confirmations, simple follow-ups
        if q_len < 15:
            for pattern in C0_PATTERNS:
                if pattern in q_lower:
                    return IntentComplexity.C0
            # Pure single-word queries or punctuation only
            if len(q.split()) <= 2 and q_len < 10:
                return IntentComplexity.C0

        # C2: long queries or queries with C2 keywords
        if q_len >= 40:
            return IntentComplexity.C2
        for kw in C2_KEYWORDS:
            if kw in q_lower:
                return IntentComplexity.C2

        # C1: everything else that is not C0 and not C2
        return IntentComplexity.C1

    def classify_semantic(self, query: str) -> IntentSemanticType:
        """Determine the dominant semantic intent via keyword scoring.

        Each pattern type is scored by the number of keyword hits, and the
        type with the highest score wins. Ties are broken by priority order
        (REASONING > COMPARISON > ACTION > FACT > ... > UNKNOWN).

        Args:
            query: The user query string.

        Returns:
            The best-matching IntentSemanticType.
        """
        q_lower = query.lower()
        scores: dict[IntentSemanticType, int] = {}

        for intent_type, patterns in INTENT_PATTERNS.items():
            score = sum(1 for p in patterns if p in q_lower)
            if score > 0:
                scores[intent_type] = score

        if not scores:
            return IntentSemanticType.UNKNOWN

        # Priority tiebreaker: more specific intents rank higher
        priority: list[IntentSemanticType] = [
            IntentSemanticType.REASONING,
            IntentSemanticType.COMPARISON,
            IntentSemanticType.ANALYSIS,
            IntentSemanticType.ACTION,
            IntentSemanticType.DEFINITION,
            IntentSemanticType.SUMMARY,
            IntentSemanticType.LIST,
            IntentSemanticType.OPINION,
            IntentSemanticType.FACT,
            IntentSemanticType.CLARIFICATION,
            IntentSemanticType.GREETING,
        ]

        max_score = max(scores.values())
        candidates = [t for t, s in scores.items() if s == max_score]

        for p in priority:
            if p in candidates:
                return p

        return IntentSemanticType.UNKNOWN

    def classify_structure(self, query: str) -> str:
        """Determine the expected answer structure type.

        Args:
            query: The user query string.

        Returns:
            One of 'procedural', 'api_spec', 'table', 'code', 'narrative',
            or 'unknown'.
        """
        q_lower = query.lower()
        best_type = "unknown"
        best_score = 0

        for struct_type, keywords in STRUCTURE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in q_lower)
            if score > best_score:
                best_score = score
                best_type = struct_type

        return best_type

    def get_route_strategy(
        self,
        complexity: IntentComplexity,
        semantic: IntentSemanticType,
    ) -> RouteStrategy:
        """Look up the routing strategy from the mapping table.

        Args:
            complexity: The classified complexity tier.
            semantic: The classified semantic type.

        Returns:
            The RouteStrategy to use.
        """
        strategy = ROUTE_MAPPING.get((complexity, semantic))
        if strategy is not None:
            return strategy

        # Fallback: reasonable defaults for unregistered combinations
        if complexity == IntentComplexity.C0:
            return RouteStrategy.DIRECT_ANSWER
        if complexity == IntentComplexity.C1:
            return RouteStrategy.RAG
        return RouteStrategy.AGENTIC_RAG

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_confidence(query: str, semantic_type: IntentSemanticType) -> float:
        """Estimate confidence in the classification result.

        Confidence is based on the ratio of matched characters to total
        query length and whether a meaningful semantic type was identified.

        Args:
            query: The user query string.
            semantic_type: The classified semantic type.

        Returns:
            A confidence score between 0.0 and 1.0.
        """
        q_lower = query.lower()
        if semantic_type == IntentSemanticType.UNKNOWN:
            return 0.3

        # Count how many characters are covered by matched patterns
        matched_chars = 0
        patterns = INTENT_PATTERNS.get(semantic_type, [])
        for p in patterns:
            idx = q_lower.find(p)
            if idx != -1:
                matched_chars += len(p)

        coverage = matched_chars / max(len(query), 1)
        base = 0.5 if semantic_type != IntentSemanticType.UNKNOWN else 0.2
        return round(min(1.0, base + coverage * 0.4), 4)
