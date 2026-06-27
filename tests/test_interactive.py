from __future__ import annotations

import unittest

from codemate import interactive


class DecodeKeyTests(unittest.TestCase):
    def test_enter_variants(self) -> None:
        self.assertEqual(interactive.decode_key(b"\r"), "enter")
        self.assertEqual(interactive.decode_key(b"\n"), "enter")

    def test_arrow_sequences(self) -> None:
        self.assertEqual(interactive.decode_key(b"\x1b", b"[A"), "up")
        self.assertEqual(interactive.decode_key(b"\x1b", b"[B"), "down")
        self.assertEqual(interactive.decode_key(b"\x1b", b"OA"), "up")

    def test_vim_keys_and_cancel(self) -> None:
        self.assertEqual(interactive.decode_key(b"k"), "up")
        self.assertEqual(interactive.decode_key(b"j"), "down")
        self.assertEqual(interactive.decode_key(b"q"), "cancel")
        self.assertEqual(interactive.decode_key(b"\x03"), "cancel")
        # lone ESC (no following bytes) cancels
        self.assertEqual(interactive.decode_key(b"\x1b", b""), "cancel")


class RenderMenuTests(unittest.TestCase):
    def test_highlights_selected_and_lists_all(self) -> None:
        options = [("Alpha", "a"), ("Beta", "b")]
        text = interactive.render_menu("pick", options, index=1, color=False)
        self.assertIn("pick", text)
        self.assertIn("  Alpha", text)
        self.assertIn("❯ Beta", text)
        self.assertIn("enter select", text)

    def test_color_adds_ansi_only_when_enabled(self) -> None:
        options = [("Alpha", "a")]
        self.assertNotIn("\033[", interactive.render_menu("", options, 0, color=False))
        self.assertIn("\033[", interactive.render_menu("", options, 0, color=True))


if __name__ == "__main__":
    unittest.main()
