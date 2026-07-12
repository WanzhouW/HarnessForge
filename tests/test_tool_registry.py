from __future__ import annotations

import unittest

from harness_forge.tools.registry import ToolRegistry, ToolResult, ToolSpec


class ToolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register(
            ToolSpec(
                name="greet",
                description="Return a greeting.",
                handler=lambda args: ToolResult.ok(message=f"hello {args['name']}"),
                parameters={"name": str},
                required=frozenset({"name"}),
            )
        )

    def test_registers_and_lists_tool(self) -> None:
        self.assertEqual(self.registry.names(), ("greet",))

    def test_invokes_registered_tool(self) -> None:
        result = self.registry.invoke("greet", {"name": "Ada"})

        self.assertTrue(result.success)
        self.assertEqual(result.output["message"], "hello Ada")

    def test_missing_required_argument_returns_structured_error(self) -> None:
        result = self.registry.invoke("greet", {})

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "TOOL_VALIDATION_ERROR")
        self.assertIn("name", result.error or "")

    def test_unknown_tool_returns_structured_error(self) -> None:
        result = self.registry.invoke("missing", {})

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "TOOL_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()

