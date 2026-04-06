import json
import os
import tempfile


def _rect_visible_in_bounds(x, y, width, height, bounds, min_visible_margin=120):
    left, top, right, bottom = bounds
    horizontal_visible = (x + min_visible_margin) < right and (x + width - min_visible_margin) > left
    vertical_visible = (y + min_visible_margin) < bottom and (y + height - min_visible_margin) > top
    return horizontal_visible and vertical_visible



def is_geometry_visible(position, screen_width, screen_height, min_visible_margin=120, display_bounds=None):
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

    candidate_bounds = []
    if isinstance(display_bounds, (list, tuple)):
        for item in display_bounds:
            if not isinstance(item, (list, tuple)) or len(item) != 4:
                continue
            try:
                candidate_bounds.append(tuple(int(value) for value in item))
            except (TypeError, ValueError):
                continue

    if candidate_bounds:
        return any(
            _rect_visible_in_bounds(x, y, width, height, bounds, min_visible_margin=min_visible_margin)
            for bounds in candidate_bounds
        )

    if screen_width <= 0 or screen_height <= 0:
        return False
    return _rect_visible_in_bounds(
        x,
        y,
        width,
        height,
        (0, 0, int(screen_width), int(screen_height)),
        min_visible_margin=min_visible_margin,
    )


def write_json_atomic(file_path, payload):
    target_path = os.path.abspath(file_path)
    parent_dir = os.path.dirname(target_path) or "."
    os.makedirs(parent_dir, exist_ok=True)

    fd = None
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=parent_dir)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = None
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_path)
    finally:
        if fd is not None:
            os.close(fd)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


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
        current = self.load() or {}
        existing_ui_state = current.get("ui_state")
        if isinstance(extra_state, dict):
            if extra_state:
                pos["ui_state"] = extra_state
            elif isinstance(existing_ui_state, dict) and existing_ui_state:
                pos["ui_state"] = existing_ui_state
        else:
            if isinstance(existing_ui_state, dict) and existing_ui_state:
                pos["ui_state"] = existing_ui_state
        write_json_atomic(self.config_file, pos)

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
        write_json_atomic(self.config_file, current)
