"""System prompt templates for the query engine.

The grounding instruction prevents hallucination by directing the LLM to
answer exclusively from the provided document context.
"""

_SYSTEM_PROMPT_TEMPLATE = """\
You are a knowledge assistant. Answer using ONLY the provided context.
If the context does not contain the answer, say so explicitly.
Do not make up information.

Context:
{context}"""


def build_system_prompt(context_text: str) -> str:
    """Build the full system prompt with the assembled document context.

    Args:
        context_text: Pre-formatted context string produced by
                      ``query_engine.context.format_context``.

    Returns:
        Complete system prompt string ready to be passed as the first message
        in the LLM messages list.
    """
    return _SYSTEM_PROMPT_TEMPLATE.format(context=context_text)
