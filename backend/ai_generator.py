import anthropic
from typing import List, Optional, Dict, Any

MAX_TOOL_ROUNDS = 2


class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to tools for searching course content and retrieving course outlines.

Tool Usage:
- `search_course_content` — for questions about specific course content or detailed educational material. Synthesize the returned chunks into accurate, fact-based answers.
- `get_course_outline` — for questions about a course's structure, syllabus, or lesson list (e.g. "what's in the MCP course", "list the lessons of X", "outline of Y"). When you use this tool, your reply MUST include the course title, the course link, and every lesson's number and title — do not summarize, omit, or truncate the lesson list.
- You may make up to TWO sequential tool calls per query. Use a second call only when the first result is insufficient — e.g. to look up a different course/lesson, refine a search, or follow up on something the first result revealed.
- Stop calling tools as soon as you can answer. Prefer one well-formed call to two speculative ones.
- If a tool yields no results, state this clearly without offering alternatives.

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without using tools.
- **Course content questions**: Use `search_course_content` first, then answer.
- **Course outline questions**: Use `get_course_outline` first, then answer.
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, tool explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

        # Pre-build base API parameters
        self.base_params = {"model": self.model, "temperature": 0, "max_tokens": 800}

    def generate_response(
        self,
        query: str,
        conversation_history: Optional[str] = None,
        tools: Optional[List] = None,
        tool_manager=None,
    ) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Tools may be invoked across up to MAX_TOOL_ROUNDS sequential rounds.
        Each round is its own API call where Claude sees prior tool results
        and decides whether to call more tools. If the cap is hit while Claude
        still wants tools, one final tools-less wrap-up call forces a textual
        answer.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """

        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        messages: List[Dict[str, Any]] = [{"role": "user", "content": query}]

        for _ in range(MAX_TOOL_ROUNDS):
            api_params = {
                **self.base_params,
                "messages": list(messages),
                "system": system_content,
            }
            if tools:
                api_params["tools"] = tools
                api_params["tool_choice"] = {"type": "auto"}

            response = self.client.messages.create(**api_params)

            if response.stop_reason != "tool_use" or tool_manager is None:
                return self._first_text_or_empty(response)

            messages.append({"role": "assistant", "content": response.content})

            try:
                tool_result_blocks = self._execute_tool_blocks(response.content, tool_manager)
            except Exception as e:
                last_tool_use_id = next(
                    (
                        b.id
                        for b in reversed(response.content)
                        if getattr(b, "type", None) == "tool_use"
                    ),
                    "unknown",
                )
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": last_tool_use_id,
                                "content": f"Tool execution failed: {e}",
                                "is_error": True,
                            }
                        ],
                    }
                )
                return self._wrap_up_without_tools(messages, system_content)

            messages.append({"role": "user", "content": tool_result_blocks})

        return self._wrap_up_without_tools(messages, system_content)

    def _execute_tool_blocks(self, content, tool_manager) -> List[Dict[str, Any]]:
        """Run every tool_use block in `content`; return matching tool_result blocks."""
        results = []
        for block in content:
            if getattr(block, "type", None) == "tool_use":
                tool_output = tool_manager.execute_tool(block.name, **block.input)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_output,
                    }
                )
        return results

    def _wrap_up_without_tools(self, messages: List[Dict[str, Any]], system_content: str) -> str:
        """Force a textual answer by calling Claude with tools omitted."""
        final_response = self.client.messages.create(
            **self.base_params,
            messages=list(messages),
            system=system_content,
        )
        return self._first_text_or_empty(final_response)

    @staticmethod
    def _first_text_or_empty(response) -> str:
        """Return the first text block's text, or "" if none exists."""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return ""
