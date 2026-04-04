"""Sprint 15 — AEGIS_TOOLS definition tests (pure computation, no mocking)."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/ai-agent-service"),
)

from src.tool_definitions import AEGIS_TOOLS


class TestToolDefinitions:

    def test_has_15_tools(self):
        """The AEGIS_TOOLS list must contain exactly 15 tool definitions."""
        assert len(AEGIS_TOOLS) == 15

    def test_all_tools_have_name(self):
        """Every tool definition must have a 'name' key."""
        for tool in AEGIS_TOOLS:
            assert "name" in tool, f"Tool missing 'name' key: {tool}"

    def test_all_tools_have_description(self):
        """Every tool definition must have a non-empty 'description' key."""
        for tool in AEGIS_TOOLS:
            assert "description" in tool, f"Tool '{tool.get('name')}' missing 'description'"
            assert len(tool["description"]) > 0, (
                f"Tool '{tool['name']}' has an empty description"
            )

    def test_all_tools_have_input_schema(self):
        """Every tool must have 'input_schema' with type == 'object'."""
        for tool in AEGIS_TOOLS:
            name = tool.get("name", "<unknown>")
            assert "input_schema" in tool, f"Tool '{name}' missing 'input_schema'"
            schema = tool["input_schema"]
            assert schema.get("type") == "object", (
                f"Tool '{name}' input_schema.type must be 'object', got '{schema.get('type')}'"
            )

    def test_tool_names_are_unique(self):
        """All 15 tool names must be unique — no duplicates allowed."""
        names = [t["name"] for t in AEGIS_TOOLS]
        assert len(set(names)) == 15, (
            f"Duplicate tool names found: {[n for n in names if names.count(n) > 1]}"
        )

    def test_get_compliance_scores_exists(self):
        """A tool named 'get_compliance_scores' must be present in AEGIS_TOOLS."""
        names = [t["name"] for t in AEGIS_TOOLS]
        assert "get_compliance_scores" in names

    def test_search_knowledge_base_has_required_param(self):
        """The 'search_knowledge_base' tool must list 'query' as a required parameter."""
        tool = next(
            (t for t in AEGIS_TOOLS if t["name"] == "search_knowledge_base"), None
        )
        assert tool is not None, "'search_knowledge_base' tool not found in AEGIS_TOOLS"

        required = tool["input_schema"].get("required", [])
        assert "query" in required, (
            "'query' must be listed as a required parameter for 'search_knowledge_base'"
        )

    def test_no_tool_has_empty_description(self):
        """Every tool description must be at least 20 characters long."""
        for tool in AEGIS_TOOLS:
            name = tool.get("name", "<unknown>")
            desc = tool.get("description", "")
            assert len(desc) > 20, (
                f"Tool '{name}' description is too short ({len(desc)} chars): '{desc}'"
            )
