"""Version-controlled prompt templates for the RAG system.

Templates are defined here with version numbers. Changes to prompts
are tracked in git history. Each template has a version string
used in cache keys to auto-invalidate cached responses when prompts change.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system_prompt: str
    user_template: str  # {context} and {query} placeholders


# -- RAG Generation Prompt --
RAG_GENERATION_PROMPT = PromptTemplate(
    name="rag_generation",
    version="3.0.0",
    system_prompt="""You are an enterprise knowledge assistant. Answer questions based solely on the provided context.

Rules:
1. If the context contains the answer, provide it clearly and concisely.
2. If the context does NOT contain the answer, say "I don't have enough information to answer this question." Do not guess.
3. Cite sources using [1], [2] notation matching the source numbers in the context.
4. Format code blocks with appropriate language tags.
5. For procedural questions, use numbered steps.
6. For comparisons, use tables when helpful.
7. Keep answers focused and relevant. Avoid tangential information.""",
    user_template="Context:\n{context}\n\nQuestion: {query}\n\nAnswer:",
)

# -- Query Rewrite Prompt --
QUERY_REWRITE_PROMPT = PromptTemplate(
    name="query_rewrite",
    version="3.0.0",
    system_prompt="You are a query rewriter. Rewrite the user's query to be more specific and self-contained, resolving any pronouns or ambiguous references based on the conversation history.",
    user_template="Conversation history:\n{history}\n\nOriginal query: {query}\n\nRewritten query:",
)

# -- Agent Decision Prompt --
AGENT_DECISION_PROMPT = PromptTemplate(
    name="agent_decision",
    version="3.0.0",
    system_prompt="""You are a RAG system router. Decide how to handle the user's query.

Output a JSON object with:
- "action": one of "retrieval", "tool_call", "direct_answer", "clarify", "refuse"
- "reason": brief explanation
- "tool_name": tool name if action is "tool_call" (optional)
- "tool_args": arguments for the tool (optional)

Rules:
- "retrieval": for knowledge questions requiring document search
- "tool_call": for math calculations, date queries requiring tools
- "direct_answer": for simple greetings, chitchat
- "clarify": for ambiguous questions
- "refuse": for harmful, illegal, or inappropriate requests""",
    user_template="User query: {query}\n\nDecision (JSON):",
)

# -- LLM Self-Score Prompt --
SELF_SCORE_PROMPT = PromptTemplate(
    name="self_score",
    version="3.0.0",
    system_prompt="Rate your previous answer on a scale of 0.0 to 1.0 based on relevance, accuracy, and completeness. Output ONLY the number.",
    user_template="Question: {query}\nContext: {context}\nAnswer: {answer}\n\nScore (0.0-1.0):",
)

# -- HyDE (Hypothetical Document) Prompt --
HYDE_PROMPT = PromptTemplate(
    name="hyde",
    version="3.0.0",
    system_prompt="Write a short passage that would answer the following question. Be factual and concise.",
    user_template="Question: {query}\n\nHypothetical answer:",
)

# -- Graph Entity Extraction Prompt --
GRAPH_EXTRACT_PROMPT = PromptTemplate(
    name="graph_extract",
    version="3.0.0",
    system_prompt="""Extract key entities and their relationships from the text.

Output JSON:
{
  "entities": [{"name": "...", "type": "...", "description": "..."}],
  "relations": [{"source": "...", "target": "...", "relation_type": "...", "description": "...", "weight": 0.8}]
}

Entity types: PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, EVENT, LOCATION
Relation types: USES, CREATED_BY, PART_OF, RELATED_TO, DEPENDS_ON, PRECEDES
Weight: 0.0-1.0 indicating relationship strength.""",
    user_template="Text:\n{text}\n\nExtracted knowledge (JSON):",
)


# Registry of all templates
ALL_TEMPLATES = {
    t.name: t
    for t in [
        RAG_GENERATION_PROMPT,
        QUERY_REWRITE_PROMPT,
        AGENT_DECISION_PROMPT,
        SELF_SCORE_PROMPT,
        HYDE_PROMPT,
        GRAPH_EXTRACT_PROMPT,
    ]
}
