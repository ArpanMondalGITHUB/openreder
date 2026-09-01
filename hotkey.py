"""
Windows System-Wide Text-to-Speech Reader (with synced line-highlight overlay)
--------------------------------------------------------------------------------
Select text in ANY app -> press Ctrl+Alt -> a floating panel shows the text
and highlights the line currently being spoken, in sync with the audio —
like karaoke/lyrics highlighting. Press Ctrl+Alt again while speaking to stop.

Install: pip install keyboard pyperclip pyttsx3 pywin32
(tkinter, used for the overlay, ships with Python already — no extra install)

Run from an elevated/admin terminal: python hotkey.py
"""

import ctypes
import keyboard
import pyperclip
import pyttsx3
import threading
import time
import tkinter as tk
import uiautomation as auto


# ---------------------------------------------------------------------------
# SOURCE-APP HIGHLIGHT (Phase 1: static box over the whole selection)
# UI Automation is Windows' accessibility API — the same thing screen
# readers use. If the focused app implements its "Text pattern" properly,
# we can ask it for the exact on-screen rectangle of the current selection,
# and draw a highlight box there instead of in our own separate panel.
# Not every app supports this, so it's built to fail quietly if not.
# ---------------------------------------------------------------------------
def get_selection_text_range():
    """Return the raw UIA TextRange for the current selection (not just its
    bounding box), so we can carve line-sized sub-ranges out of it."""
    try:
        focused = auto.GetFocusedControl()
        text_pattern = focused.GetTextPattern()
        if not text_pattern:
            return None
        selections = text_pattern.GetSelection()
        if not selections:
            return None
        return selections[0]
    except Exception as e:
        print(f"[debug] exception in get_selection_text_range: {e}")
        return None


def get_rect_for_offset_range(full_range, start_offset, end_offset):
    """Given the FULL selection's TextRange, carve out the sub-range for
    characters [start_offset, end_offset) of our copied text and return its
    on-screen bounding box — this is what lets the highlight move to a
    specific line instead of covering the whole selection."""
    try:
        sub_range = full_range.Clone()
        # Collapse the clone to exactly the selection's own start point
        # (an exact position match, not a unit-based move) so the character
        # offsets below are relative to OUR text, not the whole document.
        sub_range.MoveEndpointByRange(
            auto.TextPatternRangeEndpoint.End, sub_range, auto.TextPatternRangeEndpoint.Start
        )
        sub_range.MoveEndpointByUnit(auto.TextPatternRangeEndpoint.Start, auto.TextUnit.Character, start_offset)
        sub_range.MoveEndpointByUnit(auto.TextPatternRangeEndpoint.End, auto.TextUnit.Character, end_offset)

        rects = sub_range.GetBoundingRectangles()
        if not rects:
            return None
        lefts = [r.left for r in rects]
        tops = [r.top for r in rects]
        rights = [r.right for r in rects]
        bottoms = [r.bottom for r in rects]
        return (min(lefts), min(tops), max(rights), max(bottoms))
    except Exception as e:
        print(f"[debug] exception in get_rect_for_offset_range: {e}")
        return None


def get_selection_bounding_rect():
    """Returns (left, top, right, bottom) in screen coords, or None if the
    focused app doesn't expose a usable text selection via UI Automation."""
    try:
        focused = auto.GetFocusedControl()
        text_pattern = focused.GetTextPattern()
        if not text_pattern:
            return None
        selections = text_pattern.GetSelection()
        if not selections:
            return None
        # GetBoundingRectangles returns a list of Rect objects — one per
        # visual line the selection spans, since a wrapped selection isn't
        # a single rectangle. Combine them into one overall bounding box.
        rects = selections[0].GetBoundingRectangles()
        if not rects:
            return None
        lefts = [r.left for r in rects]
        tops = [r.top for r in rects]
        rights = [r.right for r in rects]
        bottoms = [r.bottom for r in rects]
        return (min(lefts), min(tops), max(rights), max(bottoms))
    except Exception as e:
        print(f"[debug] exception in get_selection_bounding_rect: {e}")
        return None


class HighlightBox:
    """A transparent, click-through window drawn on top of the source app,
    at the exact screen coordinates of the selection — this is what lets
    the highlight live in the ORIGINAL app instead of our status panel."""

    def __init__(self, master):
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.configure(bg='black')
        self.win.wm_attributes('-transparentcolor', 'black')  # black = see-through
        self.canvas = tk.Canvas(self.win, bg='black', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.win.withdraw()
        self.win.update_idletasks()
        self._make_click_through()

    def _make_click_through(self):
        # Without this, the highlight window would itself block clicks and
        # scrolling on the app sitting underneath it.
        GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
        hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
        styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, styles | WS_EX_LAYERED | WS_EX_TRANSPARENT
        )

    def _show(self, rect):
        left, top, right, bottom = rect
        w, h = max(int(right - left), 4), max(int(bottom - top), 4)
        self.win.geometry(f"{w}x{h}+{int(left)}+{int(top)}")
        self.canvas.config(width=w, height=h)
        self.canvas.delete('all')
        self.canvas.create_rectangle(1, 1, w - 1, h - 1, outline='#4fc3f7', width=3)
        self.win.deiconify()
        self.win.lift()

    def _hide(self):
        self.win.withdraw()

    def show(self, rect):
        self.win.after(0, lambda: self._show(rect))

    def hide(self):
        self.win.after(0, self._hide)


# ---------------------------------------------------------------------------
# STATUS OVERLAY
# Tkinter widgets can only be touched safely from the thread that created
# them (the main thread). The hotkey callback and speech both run on
# background threads, so every update goes through root.after(0, ...)
# instead of touching widgets directly — that hands the update back to the
# main thread's event loop rather than crossing threads.
# ---------------------------------------------------------------------------
class StatusOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)         # no title bar / window borders
        self.root.attributes('-topmost', True)   # always on top of other windows
        self.root.configure(bg='#1e1e1e')

        self.status_label = tk.Label(
            self.root, text="", font=('Segoe UI', 10),
            fg='#9aa0a6', bg='#1e1e1e', anchor='w'
        )
        self.status_label.pack(fill='x', padx=14, pady=(10, 0))

        # The Text widget holds the full selection, one line per visual
        # line, so we can tag-highlight whichever line is currently being
        # spoken — the karaoke-style sync the app needs.
        self.text_widget = tk.Text(
            self.root, height=6, width=52, font=('Segoe UI', 12),
            fg='#d0d0d0', bg='#1e1e1e', bd=0, highlightthickness=0,
            wrap='word', state='disabled', cursor='arrow'
        )
        self.text_widget.pack(padx=14, pady=(6, 14))
        self.text_widget.tag_configure(
            'current_line', background='#3a3d41', foreground='#4fc3f7'
        )

        self._position_bottom_center()
        self.root.withdraw()   # start hidden until the hotkey fires

    def _position_bottom_center(self):
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width, height = 520, 230
        x = (screen_w - width) // 2
        y = screen_h - height - 60
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    # --- internal, main-thread-only versions ---
    def _set_status(self, text):
        self.status_label.config(text=text)

    def _load_lines(self, lines):
        self.text_widget.config(state='normal')
        self.text_widget.delete('1.0', 'end')
        self.text_widget.insert('1.0', '\n'.join(lines))
        self.text_widget.config(state='disabled')

    def _highlight_line(self, line_number):
        self.text_widget.tag_remove('current_line', '1.0', 'end')
        start, end = f"{line_number + 1}.0", f"{line_number + 1}.end"
        self.text_widget.tag_add('current_line', start, end)
        self.text_widget.see(start)   # auto-scroll so the active line stays visible

    def _show(self):
        self.root.deiconify()
        self.root.lift()

    def _hide(self):
        self.text_widget.tag_remove('current_line', '1.0', 'end')
        self.root.withdraw()

    # --- public methods — safe to call from ANY thread ---
    def set_status(self, text):
        self.root.after(0, lambda: self._set_status(text))

    def load_lines(self, lines):
        self.root.after(0, lambda: self._load_lines(lines))

    def highlight_line(self, line_number):
        self.root.after(0, lambda: self._highlight_line(line_number))

    def show(self):
        self.root.after(0, self._show)

    def hide_after(self, ms):
        self.root.after(ms, self._hide)

    def run(self):
        def _keep_alive():
            self.root.after(200, _keep_alive)
        _keep_alive()
        self.root.mainloop()


overlay = StatusOverlay()
highlight_box = HighlightBox(overlay.root)


# ---------------------------------------------------------------------------
# TTS
# `current_engine` holds a reference to whichever pyttsx3 engine instance is
# actively speaking, so a second hotkey press (firing on a different thread)
# can reach in and call .stop() on that SAME engine object mid-speech.
# ---------------------------------------------------------------------------
current_engine = None


def speak_text(text: str) -> None:
    global current_engine

    # Normalize line endings so line-splitting and character offsets line up
    # with exactly what SAPI is speaking — mixed \r\n vs \n would otherwise
    # throw the offset-to-line mapping off.
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')

    # Precompute each line's (start, end) character offset in the full
    # string, so that when SAPI reports "currently at character X", we can
    # look up which line that falls inside.
    line_offsets = []
    cursor = 0
    for line in lines:
        line_offsets.append((cursor, cursor + len(line)))
        cursor += len(line) + 1   # +1 accounts for the '\n' we split on

    def offset_to_line(offset):
        for i, (start, end) in enumerate(line_offsets):
            if start <= offset <= end:
                return i
        return len(lines) - 1

    overlay.load_lines(lines)
    overlay.show()

    last_line = {'index': -1}

    # SAPI5 fires this once per word, with the character offset of that
    # word inside the text we gave it — this is what makes real-time,
    # audio-synced highlighting possible instead of a fixed-timer guess.
    def on_word(name, location, length):
        line_index = offset_to_line(location)
        if line_index != last_line['index']:
            last_line['index'] = line_index
            overlay.highlight_line(line_index)

    engine = pyttsx3.init()
    current_engine = engine
    try:
        engine.setProperty('rate', 175)
        engine.connect('started-word', on_word)
        engine.say(text)
        engine.runAndWait()   # blocks here until speech ends OR .stop() is called
    finally:
        engine.stop()
        current_engine = None


is_speaking = False


def wait_for_clipboard_change(original: str, timeout: float = 3.0, poll_interval: float = 0.05) -> str:
    """
    Poll the clipboard until it differs from `original`, instead of guessing
    a fixed delay — longer selections can take noticeably longer to finish
    writing to the clipboard. `timeout` is a safety net in case nothing was
    actually copied.
    """
    start = time.time()
    while time.time() - start < timeout:
        current = pyperclip.paste()
        if current != original:
            return current
        time.sleep(poll_interval)
    return pyperclip.paste()   # give up — return whatever's there


def read_selected_text():
    global is_speaking, current_engine

    # Second press WHILE speaking -> interrupt instead of starting fresh.
    if is_speaking:
        if current_engine is not None:
            current_engine.stop()
        overlay.set_status("Stopped")
        overlay.hide_after(800)
        is_speaking = False
        return

    overlay.set_status("Listening...")
    overlay.show()

    # Save whatever's currently in the clipboard so we can restore it.
    original_clipboard = pyperclip.paste()

    # Release the hotkey's own modifier keys first — otherwise Ctrl and Alt
    # are still physically held down, and the OS sees Ctrl+Alt+C instead of
    # a clean copy command.
    keyboard.release('ctrl')
    keyboard.release('alt')
    time.sleep(0.05)

    keyboard.send('ctrl+c')
    selected_text = wait_for_clipboard_change(original_clipboard)

    if not selected_text or selected_text == original_clipboard:
        overlay.set_status("Nothing selected")
        overlay.hide_after(1200)
        return

    pyperclip.copy(original_clipboard)   # restore the user's clipboard

    overlay.set_status("Speaking")
    is_speaking = True

    def run():
        global is_speaking
        try:
            speak_text(selected_text)
        finally:
            is_speaking = False
            overlay.hide_after(800)

    threading.Thread(target=run, daemon=True).start()


# Register the global hotkey. The `keyboard` library runs its own listener
# thread internally once a hotkey is registered.
keyboard.add_hotkey('ctrl+alt', read_selected_text)

# The main thread now runs the GUI's event loop instead of keyboard.wait() —
# this is what keeps the whole app alive.
overlay.run()