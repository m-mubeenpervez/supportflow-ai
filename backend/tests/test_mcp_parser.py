
import pytest
from types import SimpleNamespace

from app.mcp_parser import parse_mcp_result, MCPResponseError


def make_result(text=None, structured=None, is_error=False):
    content = []

    if text is not None:
        content.append(
            SimpleNamespace(type="text", text=text)
        )

    return SimpleNamespace(
        isError=is_error,
        structuredContent=structured,
        content=content,
    )


def test_parse_json_dictionary():
    result = make_result(text='{"status": "delivered"}')

    data = parse_mcp_result(result)

    assert data == {"status": "delivered"}


def test_parse_json_list():
    result = make_result(text='[{"title": "Refund Policy"}]')

    data = parse_mcp_result(result)

    assert data == [{"title": "Refund Policy"}]


def test_parse_structured_content():
    result = make_result(
        structured={"id": "ORD1023"}
    )

    data = parse_mcp_result(result)

    assert data == {"id": "ORD1023"}


def test_reject_mcp_error():
    result = make_result(
        text='{"error": "Tool failed"}',
        is_error=True,
    )

    with pytest.raises(MCPResponseError):
        parse_mcp_result(result)


def test_reject_invalid_json():
    result = make_result(text="not valid JSON")

    with pytest.raises(MCPResponseError):
        parse_mcp_result(result)


def test_reject_unsupported_structured_data():
    result = make_result(structured="invalid")

    with pytest.raises(MCPResponseError):
        parse_mcp_result(result)
