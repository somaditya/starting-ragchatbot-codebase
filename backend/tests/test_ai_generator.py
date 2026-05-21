"""Tests for AIGenerator's tool dispatch logic.

These are pure unit tests — anthropic.Anthropic is patched so no API
traffic happens and the response shape is deterministic.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ai_generator import AIGenerator


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name, inp, id="tool_1"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id)


def _response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


@pytest.fixture
def mock_anthropic_class():
    with patch("ai_generator.anthropic.Anthropic") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


@pytest.fixture
def gen(mock_anthropic_class):
    return AIGenerator(api_key="fake-key", model="claude-test")


def test_tools_are_forwarded_to_api(mock_anthropic_class, gen):
    mock_anthropic_class.messages.create.return_value = _response(
        [_text_block("hello")], stop_reason="end_turn"
    )
    tools = [{"name": "search_course_content", "input_schema": {}}]
    gen.generate_response(query="q", tools=tools)

    call_kwargs = mock_anthropic_class.messages.create.call_args.kwargs
    assert call_kwargs["tools"] == tools
    assert call_kwargs["tool_choice"] == {"type": "auto"}


def test_no_tools_means_no_tool_choice(mock_anthropic_class, gen):
    mock_anthropic_class.messages.create.return_value = _response(
        [_text_block("hello")], stop_reason="end_turn"
    )
    gen.generate_response(query="q")
    call_kwargs = mock_anthropic_class.messages.create.call_args.kwargs
    assert "tools" not in call_kwargs
    assert "tool_choice" not in call_kwargs


def test_system_prompt_is_sent_and_includes_history(mock_anthropic_class, gen):
    mock_anthropic_class.messages.create.return_value = _response(
        [_text_block("hi")], stop_reason="end_turn"
    )
    gen.generate_response(query="q", conversation_history="User: hi\nAssistant: hey")
    call_kwargs = mock_anthropic_class.messages.create.call_args.kwargs
    assert AIGenerator.SYSTEM_PROMPT.strip() in call_kwargs["system"]
    assert "Previous conversation:" in call_kwargs["system"]
    assert "User: hi" in call_kwargs["system"]


def test_direct_response_when_stop_reason_end_turn(mock_anthropic_class, gen):
    mock_anthropic_class.messages.create.return_value = _response(
        [_text_block("the answer")], stop_reason="end_turn"
    )
    out = gen.generate_response(query="q")
    assert out == "the answer"
    assert mock_anthropic_class.messages.create.call_count == 1


def test_tool_use_triggers_handle_tool_execution(mock_anthropic_class, gen):
    first = _response(
        [_tool_use_block("search_course_content", {"query": "foo"}, id="tu_1")],
        stop_reason="tool_use",
    )
    second = _response([_text_block("final")], stop_reason="end_turn")
    mock_anthropic_class.messages.create.side_effect = [first, second]

    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "tool result body"

    out = gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content", "input_schema": {}}],
        tool_manager=tool_manager,
    )

    assert out == "final"
    tool_manager.execute_tool.assert_called_once_with("search_course_content", query="foo")
    assert mock_anthropic_class.messages.create.call_count == 2


def test_tool_result_appended_as_user_message(mock_anthropic_class, gen):
    first = _response(
        [_tool_use_block("search_course_content", {"query": "foo"}, id="tu_42")],
        stop_reason="tool_use",
    )
    second = _response([_text_block("final")], stop_reason="end_turn")
    mock_anthropic_class.messages.create.side_effect = [first, second]

    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "RESULT_BODY"

    gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content", "input_schema": {}}],
        tool_manager=tool_manager,
    )

    second_kwargs = mock_anthropic_class.messages.create.call_args_list[1].kwargs
    messages = second_kwargs["messages"]
    last = messages[-1]
    assert last["role"] == "user"
    assert isinstance(last["content"], list) and len(last["content"]) == 1
    block = last["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "tu_42"
    assert block["content"] == "RESULT_BODY"


def test_final_text_returned(mock_anthropic_class, gen):
    first = _response(
        [_tool_use_block("search_course_content", {"query": "q"}, id="t")],
        stop_reason="tool_use",
    )
    second = _response([_text_block("the final answer")], stop_reason="end_turn")
    mock_anthropic_class.messages.create.side_effect = [first, second]

    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "tr"

    out = gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content", "input_schema": {}}],
        tool_manager=tool_manager,
    )
    assert out == "the final answer"


# ---------------------------------------------------------------------------
# Sequential / multi-round tool-use tests
# ---------------------------------------------------------------------------


def test_two_rounds_happy_path(mock_anthropic_class, gen):
    first = _response(
        [_tool_use_block("search_course_content", {"query": "foo"}, id="tu_1")],
        stop_reason="tool_use",
    )
    second = _response(
        [_tool_use_block("get_course_outline", {"course_name": "bar"}, id="tu_2")],
        stop_reason="tool_use",
    )
    third = _response([_text_block("the final answer")], stop_reason="end_turn")
    mock_anthropic_class.messages.create.side_effect = [first, second, third]

    tool_manager = MagicMock()
    tool_manager.execute_tool.side_effect = ["result one", "outline two"]

    out = gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content", "input_schema": {}}],
        tool_manager=tool_manager,
    )

    assert out == "the final answer"
    assert mock_anthropic_class.messages.create.call_count == 3
    assert tool_manager.execute_tool.call_count == 2
    tool_manager.execute_tool.assert_any_call("search_course_content", query="foo")
    tool_manager.execute_tool.assert_any_call("get_course_outline", course_name="bar")


def test_tools_present_on_rounds_one_and_two(mock_anthropic_class, gen):
    tools = [{"name": "search_course_content", "input_schema": {}}]
    first = _response(
        [_tool_use_block("search_course_content", {"query": "foo"}, id="tu_1")],
        stop_reason="tool_use",
    )
    second = _response(
        [_tool_use_block("get_course_outline", {"course_name": "bar"}, id="tu_2")],
        stop_reason="tool_use",
    )
    third = _response([_text_block("done")], stop_reason="end_turn")
    mock_anthropic_class.messages.create.side_effect = [first, second, third]

    tool_manager = MagicMock()
    tool_manager.execute_tool.side_effect = ["r1", "r2"]

    gen.generate_response(query="q", tools=tools, tool_manager=tool_manager)

    calls = mock_anthropic_class.messages.create.call_args_list
    assert calls[0].kwargs["tools"] == tools
    assert calls[0].kwargs["tool_choice"] == {"type": "auto"}
    assert calls[1].kwargs["tools"] == tools
    assert calls[1].kwargs["tool_choice"] == {"type": "auto"}


def test_wrap_up_call_omits_tools_when_cap_hit(mock_anthropic_class, gen):
    first = _response(
        [_tool_use_block("search_course_content", {"query": "foo"}, id="tu_1")],
        stop_reason="tool_use",
    )
    second = _response(
        [_tool_use_block("get_course_outline", {"course_name": "bar"}, id="tu_2")],
        stop_reason="tool_use",
    )
    third = _response([_text_block("wrap-up")], stop_reason="end_turn")
    mock_anthropic_class.messages.create.side_effect = [first, second, third]

    tool_manager = MagicMock()
    tool_manager.execute_tool.side_effect = ["r1", "r2"]

    out = gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content", "input_schema": {}}],
        tool_manager=tool_manager,
    )

    assert out == "wrap-up"
    wrap_kwargs = mock_anthropic_class.messages.create.call_args_list[2].kwargs
    assert "tools" not in wrap_kwargs
    assert "tool_choice" not in wrap_kwargs


def test_round_two_end_turn_means_no_third_call(mock_anthropic_class, gen):
    first = _response(
        [_tool_use_block("search_course_content", {"query": "foo"}, id="tu_1")],
        stop_reason="tool_use",
    )
    second = _response([_text_block("answered in round 2")], stop_reason="end_turn")
    mock_anthropic_class.messages.create.side_effect = [first, second]

    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "r1"

    out = gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content", "input_schema": {}}],
        tool_manager=tool_manager,
    )

    assert out == "answered in round 2"
    assert mock_anthropic_class.messages.create.call_count == 2
    tool_manager.execute_tool.assert_called_once()


def test_messages_accumulate_across_rounds(mock_anthropic_class, gen):
    first_content = [_tool_use_block("search_course_content", {"query": "foo"}, id="tu_1")]
    second_content = [_tool_use_block("get_course_outline", {"course_name": "bar"}, id="tu_2")]
    first = _response(first_content, stop_reason="tool_use")
    second = _response(second_content, stop_reason="tool_use")
    third = _response([_text_block("done")], stop_reason="end_turn")
    mock_anthropic_class.messages.create.side_effect = [first, second, third]

    tool_manager = MagicMock()
    tool_manager.execute_tool.side_effect = ["result one", "outline two"]

    gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content", "input_schema": {}}],
        tool_manager=tool_manager,
    )

    wrap_msgs = mock_anthropic_class.messages.create.call_args_list[2].kwargs["messages"]
    assert len(wrap_msgs) == 5

    # user query
    assert wrap_msgs[0] == {"role": "user", "content": "q"}
    # assistant round 1 tool_use
    assert wrap_msgs[1]["role"] == "assistant"
    assert wrap_msgs[1]["content"] == first_content
    # user round 1 tool_result
    assert wrap_msgs[2]["role"] == "user"
    assert wrap_msgs[2]["content"][0]["type"] == "tool_result"
    assert wrap_msgs[2]["content"][0]["tool_use_id"] == "tu_1"
    assert wrap_msgs[2]["content"][0]["content"] == "result one"
    # assistant round 2 tool_use
    assert wrap_msgs[3]["role"] == "assistant"
    assert wrap_msgs[3]["content"] == second_content
    # user round 2 tool_result
    assert wrap_msgs[4]["role"] == "user"
    assert wrap_msgs[4]["content"][0]["type"] == "tool_result"
    assert wrap_msgs[4]["content"][0]["tool_use_id"] == "tu_2"
    assert wrap_msgs[4]["content"][0]["content"] == "outline two"


def test_tool_execution_exception_terminates_with_wrap_up(mock_anthropic_class, gen):
    first = _response(
        [_tool_use_block("search_course_content", {"query": "foo"}, id="tu_err")],
        stop_reason="tool_use",
    )
    wrap_up = _response([_text_block("sorry, tool failed")], stop_reason="end_turn")
    mock_anthropic_class.messages.create.side_effect = [first, wrap_up]

    tool_manager = MagicMock()
    tool_manager.execute_tool.side_effect = RuntimeError("boom")

    out = gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content", "input_schema": {}}],
        tool_manager=tool_manager,
    )

    assert out == "sorry, tool failed"
    assert mock_anthropic_class.messages.create.call_count == 2
    tool_manager.execute_tool.assert_called_once()

    wrap_kwargs = mock_anthropic_class.messages.create.call_args_list[1].kwargs
    assert "tools" not in wrap_kwargs
    last = wrap_kwargs["messages"][-1]
    assert last["role"] == "user"
    err_block = last["content"][0]
    assert err_block["type"] == "tool_result"
    assert err_block["tool_use_id"] == "tu_err"
    assert err_block.get("is_error") is True
    assert "boom" in err_block["content"]


def test_tool_use_with_no_tool_manager_returns_text_safely(mock_anthropic_class, gen):
    resp = _response(
        [
            _tool_use_block("search_course_content", {"query": "foo"}, id="tu_1"),
            _text_block("fallback"),
        ],
        stop_reason="tool_use",
    )
    mock_anthropic_class.messages.create.return_value = resp

    out = gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content", "input_schema": {}}],
    )

    assert out == "fallback"
    assert mock_anthropic_class.messages.create.call_count == 1
