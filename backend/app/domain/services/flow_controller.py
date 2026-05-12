"""Pre-checks and post-enhancements for the RAG pipeline flow.

The FlowController blocks unsafe or off-topic queries before they reach
the retrieval pipeline, and appends warnings / suggestions to low-confidence
responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FlowDecision(StrEnum):
    """Decision after pre-checking a user query."""

    PASS = "pass"              # Normal processing
    REFUSE = "refuse"          # Block the query entirely
    CLARIFY = "clarify"        # Ask the user for more detail


@dataclass(frozen=True)
class FlowControlResult:
    """Outcome of a flow-control pre-check.

    Attributes:
        decision: PASS, REFUSE, or CLARIFY.
        reason: Short machine-readable tag explaining the decision.
        message: User-facing message (refusal note or clarification prompt).
    """

    decision: FlowDecision = FlowDecision.PASS
    reason: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# Refusal patterns (safety / security)
# ---------------------------------------------------------------------------

REFUSE_PATTERNS: list[str] = [
    # ---- Gambling / betting ----
    "赌博", "博彩", "赌场", "下注", "投注", "赌球", "赌马",
    "彩票", "刮刮乐", "老虎机", "轮盘", "百家乐", "炸金花",
    "赌钱", "赌", "casino", "gambling", "betting", "lottery",
    "poker", "blackjack", "roulette",
    # ---- Pornography / adult content ----
    "色情", "情色", "成人", "淫秽", "裸露", "裸体",
    "av", "黄色", "三级片", " porn ", "pornography", "adult content",
    "nsfw", "xxx", "sex", "erotic",
    # ---- Code generation for malicious purposes ----
    "写病毒", "写木马", "写恶意", "写蠕虫", "编写病毒",
    "生成恶意代码", "生成shellcode", "生成恶意软件",
    "bypass antivirus", "绕过防火墙", "绕过杀毒",
    "malware", "ransomware", "trojan", "worm", "virus code",
    "keylogger", "backdoor", "rootkit", "exploit code",
    # ---- Hacking / intrusion ----
    "黑客", "入侵", "攻击", "渗透", "漏洞利用", "提权",
    "sql注入", "xss攻击", "csrf攻击", "ddos", "cc攻击",
    "端口扫描", "暴力破解", "钓鱼", "phishing",
    "hacking", "hack", "intrusion", "penetration",
    "exploit", "crack", "keygen", "reverse engineering malware",
    # ---- PII / personal data requests ----
    "身份证号", "手机号", "银行卡号", "信用卡号", "密码",
    "社保号", "护照号", "驾驶证", "住址", "家庭住址",
    "个人隐私", "个人信息", "公民身份",
    "id number", "social security", "credit card number",
    "passport number", "driver license", "bank account",
    "cvv", "pin code",
    # ---- Illegal / harmful activities ----
    "毒品", "制毒", "贩毒", "吸毒", "毒品制作",
    "枪支", "弹药", "爆炸物", "制作炸弹",
    "杀人", "绑架", "诈骗", "洗钱",
    "drugs", "cocaine", "heroin", "meth", "weapon",
    "bomb", "explosive", "murder", "kidnap", "money laundering",
    "terrorism", "terrorist",
]

# ---------------------------------------------------------------------------
# Greeting patterns (short social queries, no retrieval needed)
# ---------------------------------------------------------------------------

GREETING_PATTERNS: list[str] = [
    # Chinese
    "你好", "您好", "嗨", "哈喽", "嗨喽", "嘿",
    "早上好", "上午好", "中午好", "下午好", "晚上好",
    "你好吗", "你怎么样", "在吗", "在不在", "hello", "hi",
    # English
    "good morning", "good afternoon", "good evening",
    "how are you", "howdy", "greetings", "hey there",
    "what's up", "sup", "nice to meet you",
]

# ---------------------------------------------------------------------------
# Clarification patterns (vague queries that need more context)
# ---------------------------------------------------------------------------

CLARIFY_PATTERNS: list[str] = [
    # Chinese
    "这个", "那个", "它", "它们", "他", "她", "他们",
    "帮我查一下", "帮我看看", "帮我找找", "查一下",
    "那个什么", "那个东西", "这个东西",
    "你能帮我吗", "有问题", "我想问",
    "关于这个", "关于那个",
    # English
    "this", "that", "it", "they", "them", "i have a question",
    "can you help me", "i need help", "tell me something",
    "i want to ask", "about this", "about that",
    "help me with", "i'm looking for",
]


class FlowController:
    """Pre-checks queries before expensive pipeline execution and
    post-enhances responses with confidence-based annotations.

    All checks are pure rule-based (no I/O, no LLM calls).
    """

    # Expose patterns as class-level constants for easy customisation.
    REFUSE_PATTERNS: list[str] = REFUSE_PATTERNS
    GREETING_PATTERNS: list[str] = GREETING_PATTERNS
    CLARIFY_PATTERNS: list[str] = CLARIFY_PATTERNS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pre_check(self, query: str) -> FlowControlResult:
        """Check whether the query should be refused, clarified, or passed.

        The check order is:
        1. Refuse -- query matches a forbidden pattern.
        2. Clarify -- query is too vague or underspecified.
        3. Pass -- everything else.

        Args:
            query: The raw user query string.

        Returns:
            A FlowControlResult with the decision and a user-facing message.
        """
        q_lower = query.strip().lower()

        # ---- Refusal check ------------------------------------------------
        for pattern in self.REFUSE_PATTERNS:
            if pattern in q_lower:
                return FlowControlResult(
                    decision=FlowDecision.REFUSE,
                    reason="refuse_unsafe_content",
                    message="I am sorry, but I cannot assist with this request "
                            "as it involves prohibited content.",
                )

        # ---- Clarification check ------------------------------------------
        if len(query.strip()) < 3:
            return FlowControlResult(
                decision=FlowDecision.CLARIFY,
                reason="clarify_too_short",
                message="Your query seems too short. Could you please provide "
                        "more details so I can better assist you?",
            )

        for pattern in self.CLARIFY_PATTERNS:
            if q_lower == pattern or q_lower.startswith(pattern):
                return FlowControlResult(
                    decision=FlowDecision.CLARIFY,
                    reason="clarify_vague_query",
                    message="Your query is a bit vague. Could you please "
                            "specify what you are looking for?",
                )

        # ---- Greeting shortcut (pass-through, will be handled by intent) --
        return FlowControlResult(
            decision=FlowDecision.PASS,
            reason="",
            message="",
        )

    def post_enhance(self, answer: str, confidence: float) -> str:
        """Optionally annotate the final answer based on confidence.

        - Low confidence (< 0.3): prepend a disclaimer.
        - Medium confidence (0.3-0.6): append a suggestion to verify.
        - High confidence (> 0.6): return as-is.

        Args:
            answer: The generated answer text.
            confidence: The confidence score (0.0 to 1.0).

        Returns:
            The answer, optionally enhanced with a warning or suggestion.
        """
        if confidence < 0.3:
            disclaimer = (
                "[Note: The confidence in this answer is low. "
                "Please verify the information from additional sources.]\n\n"
            )
            return disclaimer + answer

        if confidence < 0.6:
            suggestion = (
                "\n\n---\n"
                "*I recommend verifying this information with additional sources "
                "as the confidence level is moderate.*"
            )
            return answer + suggestion

        return answer
