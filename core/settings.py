import json
import os


def is_geometry_visible(position, screen_width, screen_height, min_visible_margin=120):
    if not position:
        return False

    try:
        x = int(position.get("x", 0))
        y = int(position.get("y", 0))
        width = int(position.get("width", 0))
        height = int(position.get("height", 0))
    except (TypeError, ValueError, AttributeError):
        return False

    if width <= 0 or height <= 0:
        return False
    if screen_width <= 0 or screen_height <= 0:
        return False

    horizontal_visible = (x + min_visible_margin) < screen_width and (x + width - min_visible_margin) > 0
    vertical_visible = (y + min_visible_margin) < screen_height and (y + height - min_visible_margin) > 0
    return horizontal_visible and vertical_visible


class WindowPositionRepository:
    def __init__(self, config_file):
        self.config_file = config_file

    def load(self):
        if not os.path.exists(self.config_file):
            return None
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save(self, root_window, extra_state=None):
        pos = {
            "x": root_window.winfo_x(),
            "y": root_window.winfo_y(),
            "width": root_window.winfo_width(),
            "height": root_window.winfo_height(),
        }
        if isinstance(extra_state, dict) and extra_state:
            pos["ui_state"] = extra_state
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(pos, f, ensure_ascii=False, indent=2)

    def get_ui_state(self):
        data = self.load() or {}
        ui_state = data.get("ui_state")
        return ui_state if isinstance(ui_state, dict) else {}

    def save_ui_state(self, root_window, ui_state):
        current = self.load() or {}
        if not isinstance(ui_state, dict):
            ui_state = {}
        current["ui_state"] = ui_state
        current.update({
            "x": root_window.winfo_x(),
            "y": root_window.winfo_y(),
            "width": root_window.winfo_width(),
            "height": root_window.winfo_height(),
        })
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
