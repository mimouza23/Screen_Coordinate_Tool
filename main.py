import sys
import os
import json
import math
from datetime import datetime
from typing import List, Optional, Union, Tuple, Dict

# This is to use native pixel resolution
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QMenu, QMessageBox, QFileDialog, QInputDialog, QAbstractItemView,
    QStyle, QStyledItemDelegate, QLineEdit, QFrame, QTreeWidgetItemIterator
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QSize, QEvent, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QCursor, QBrush, QIcon, QPalette
)



class CoordinateItem:
    def __init__(self, x: int, y: int, name: str = "", timestamp: Optional[str] = None):
        self.x = x
        self.y = y
        self.name = name or f"Point ({x}, {y})"
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self):
        return {"type": "coordinate", "x": self.x, "y": self.y, "name": self.name, "timestamp": self.timestamp}

class MeasurementItem:
    def __init__(self, x1, y1, x2, y2, distance, name="", timestamp=None, auto_aligned=False):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.distance = distance
        self.name = name or f"Measurement {int(distance)}px"
        self.timestamp = timestamp or datetime.now().isoformat()
        self.auto_aligned = auto_aligned

    def to_dict(self):
        return {
            "type": "measurement", "x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2,
            "distance": self.distance, "name": self.name, "timestamp": self.timestamp, "auto_aligned": self.auto_aligned
        }

class FolderItem:
    def __init__(self, name="", timestamp=None, items=None, expanded=True):
        self.name = name or "New Folder"
        self.timestamp = timestamp or datetime.now().isoformat()
        self.items = items if items is not None else []
        self.expanded = expanded

    def to_dict(self):
        return {
            "type": "folder", "name": self.name, "timestamp": self.timestamp,
            "expanded": self.expanded, "items": [item.to_dict() for item in self.items]
        }




class DataStore:
    DATA_FILE = os.path.expanduser("~/.screen_coordinate_tool_qt.json")

    def __init__(self):
        self.root_items = []
        self.load()

    def save_from_tree(self, tree_widget: QTreeWidget):
        """Rebuilds data model from the UI Tree structure and saves it."""
        self.root_items = self._serialize_tree(tree_widget.invisibleRootItem())
        self._save_to_disk()

    def _serialize_tree(self, parent_item: QTreeWidgetItem) -> List:
        items = []
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            data = child.data(0, Qt.UserRole)
            
            # The text in column 0 might have the emoji prefix, we want the raw name.
            raw_text = child.text(0)
            clean_name = raw_text
            for prefix in ["📍 ", "📏 ", "📁 "]:
                if clean_name.startswith(prefix):
                    clean_name = clean_name[len(prefix):]
            
            if isinstance(data, FolderItem):
                data.expanded = child.isExpanded()
                data.name = clean_name
                data.items = self._serialize_tree(child)
                items.append(data)
            else:
                data.name = clean_name
                items.append(data)
        return items

    def _save_to_disk(self):
        try:
            data = [item.to_dict() for item in self.root_items]
            with open(self.DATA_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving: {e}")

    def load(self):
        if not os.path.exists(self.DATA_FILE):
            return
        try:
            with open(self.DATA_FILE, "r") as f:
                raw_data = json.load(f)
                self.root_items = self._parse_items(raw_data)
        except Exception as e:
            print(f"Error loading: {e}")

    def _parse_items(self, json_list):
        items = []
        for d in json_list:
            if d['type'] == 'coordinate':
                items.append(CoordinateItem(d['x'], d['y'], d.get('name'), d.get('timestamp')))
            elif d['type'] == 'measurement':
                items.append(MeasurementItem(d['x1'], d['y1'], d['x2'], d['y2'], d['distance'], d.get('name'), d.get('timestamp'), d.get('auto_aligned')))
            elif d['type'] == 'folder':
                folder = FolderItem(d['name'], d.get('timestamp'), expanded=d.get('expanded', True))
                folder.items = self._parse_items(d.get('items', []))
                items.append(folder)
        return items



class SmartRenameDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        # When entering edit mode, show the text WITHOUT the emoji prefix
        text = index.model().data(index, Qt.EditRole)
        for prefix in ["📍 ", "📏 ", "📁 "]:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        editor.setText(text)

    def setModelData(self, editor, model, index):
        # When saving, re-apply the correct emoji prefix based on item type
        new_text = editor.text()
        data = index.data(Qt.UserRole)
        
        prefix = ""
        if isinstance(data, CoordinateItem):
            prefix = "📍 "
        elif isinstance(data, MeasurementItem):
            prefix = "📏 "
        elif isinstance(data, FolderItem):
            prefix = "📁 "
            
        if not new_text.startswith(prefix):
            final_text = prefix + new_text
        else:
            final_text = new_text
            
        model.setData(index, final_text, Qt.EditRole)



class HistoryTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setHeaderLabels(["Item", "Details"])
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        
        # Visual styling improvements for hierarchy
        self.setAlternatingRowColors(True)
        self.setIndentation(25) # Deeper indentation to make folders clearer
        
        # Install Delegate
        self.setItemDelegateForColumn(0, SmartRenameDelegate(self))

    def dropEvent(self, event):
        super().dropEvent(event)
        self.sanitize_tree()
        if self.window():
            self.window().recalculate_folder_counts()
            self.window().save_data()

    def sanitize_tree(self):
        root = self.invisibleRootItem()
        self._check_node(root)

    def _check_node(self, parent):
        for i in range(parent.childCount() - 1, -1, -1):
            child = parent.child(i)
            data = child.data(0, Qt.UserRole)
            
            if not isinstance(data, FolderItem) and child.childCount() > 0:
                take_children = []
                while child.childCount() > 0:
                    take_children.append(child.takeChild(0))
                parent.insertChildren(i + 1, take_children)
            
            if isinstance(data, FolderItem):
                self._check_node(child)




class OverlayWindow(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        # --- Window Setup ---
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.showFullScreen()
        self.setMouseTracking(True)
        
        # State
        self.cursor_pos = QPoint(0, 0)
        self.corner_pos = 3 # 0=TR, 1=BR, 2=BL, 3=TL
        self.capture_mode = "normal" # "normal", "ruler", "edit"
        self.ruler_start = None
        self.shift_pressed = False
        self.show_help = True
        self.notifications = [] 
        
        # Edit Mode State
        self.session_items = [] # List of tuples: (item_model, rect/point)
        self.selected_item_index = -1
        
        self.setCursor(Qt.CrossCursor)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Edit Mode Markers
        if self.capture_mode == "edit":
            self.draw_edit_markers(painter)

        # 2. Draw Ruler if active
        if self.capture_mode == "ruler" and self.ruler_start:
            self.draw_ruler(painter)

        # 3. UI Elements
        self.draw_coordinate_label(painter)
        
        if self.show_help:
            self.draw_help(painter)
        else:
            self.draw_help_hint(painter)

        self.draw_notifications(painter)

        # Edit Mode Banner
        if self.capture_mode == "edit":
             self.draw_text_with_bg(painter, "-- EDIT MODE --", self.rect().width()/2, 50, QColor(0, 255, 255), bg_alpha=200)

    def draw_edit_markers(self, painter):
        # Bright Orange
        marker_color = QColor(255, 140, 0) 
        
        # Text settings
        fm = painter.fontMetrics()
        screen_w = self.rect().width()

        for i, (item, _) in enumerate(self.session_items):
            is_selected = (i == self.selected_item_index)
            
            # Thick black outline
            pen = QPen(Qt.black, 3) 
            if is_selected:
                pen.setColor(Qt.cyan) # Highlight selection
                pen.setWidth(4)
                
            painter.setPen(pen)
            painter.setBrush(QBrush(marker_color))

            label_text = ""
            label_pos = QPoint(0,0)
            point_radius = 10 # Big points

            if isinstance(item, CoordinateItem):
                # Draw Point
                painter.drawEllipse(item.x - point_radius, item.y - point_radius, point_radius * 2, point_radius * 2)
                
                label_text = f"{item.name} ({item.x}, {item.y})"
                
                # Smart Positioning
                text_width = fm.width(label_text) + 15
                if item.x + point_radius + text_width > screen_w:
                    # Place on Left
                    label_pos = QPoint(item.x - point_radius - 10, item.y)
                else:
                    # Place on Right
                    label_pos = QPoint(item.x + point_radius + 10, item.y)
                
                # If text is on left, we need to shift the draw coordinate because draw_text_with_bg centers on X
                # But my helper centers it? Let's check helper: drawRect(x - w/2)
                # Helper centers text around X.
                
                # Let's adjust logic for the helper
                offset_x = 0
                if item.x + point_radius + text_width > screen_w:
                    offset_x = - (text_width / 2) - point_radius
                else:
                    offset_x = (text_width / 2) + point_radius
                
                label_pos = QPoint(int(item.x + offset_x), item.y)


            elif isinstance(item, MeasurementItem):
                # Draw thicker line for measurement
                line_pen = QPen(marker_color, 4)
                if is_selected: line_pen = QPen(Qt.cyan, 4)
                
                # Draw black outline for line
                outline_pen = QPen(Qt.black, 6)
                painter.setPen(outline_pen)
                painter.drawLine(int(item.x1), int(item.y1), int(item.x2), int(item.y2))
                
                # Draw actual colored line
                painter.setPen(line_pen)
                painter.drawLine(int(item.x1), int(item.y1), int(item.x2), int(item.y2))
                
                # Draw end points
                painter.setPen(pen)
                painter.drawEllipse(int(item.x1) - point_radius, int(item.y1) - point_radius, point_radius * 2, point_radius * 2)
                painter.drawEllipse(int(item.x2) - point_radius, int(item.y2) - point_radius, point_radius * 2, point_radius * 2)

                mid_x = (item.x1 + item.x2) / 2
                mid_y = (item.y1 + item.y2) / 2
                label_text = f"{item.name} [{int(item.distance)}px]"
                label_pos = QPoint(int(mid_x), int(mid_y) - 20)

            # Draw Label
            if label_text:
                self.draw_text_with_bg(painter, label_text, label_pos.x(), label_pos.y(), QColor(255, 255, 255), bg_alpha=160)

    def draw_ruler(self, painter):
        start = self.ruler_start
        end = self.cursor_pos
        
        if not self.shift_pressed:
            dx = abs(end.x() - start.x())
            dy = abs(end.y() - start.y())
            if dx > dy * 10: end = QPoint(end.x(), start.y())
            elif dy > dx * 10: end = QPoint(start.x(), end.y())

        # Draw Outline (Black)
        pen_outline = QPen(Qt.black)
        pen_outline.setWidth(4)
        painter.setPen(pen_outline)
        painter.drawLine(start, end)
        painter.setBrush(Qt.black)
        painter.drawEllipse(start, 5, 5)
        painter.drawEllipse(end, 5, 5)

        # Draw Line (Yellow)
        pen = QPen(QColor(255, 255, 0))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(start, end)

        # Draw Endpoints (Red)
        painter.setBrush(QBrush(QColor(255, 0, 0)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(start, 4, 4)
        painter.drawEllipse(end, 4, 4)

        # Draw Text
        dist = math.sqrt((end.x() - start.x())**2 + (end.y() - start.y())**2)
        mid = (start + end) / 2
        text = f"{int(dist)}px"
        
        # White text on semi-transparent black
        self.draw_text_with_bg(painter, text, mid.x(), mid.y() - 20, QColor(255, 255, 255), bg_alpha=160)

    def draw_coordinate_label(self, painter):
        text = f"X: {self.cursor_pos.x():04d}  Y: {self.cursor_pos.y():04d}"
        screen_geo = self.rect()
        margin = 20
        font = QFont("Monospace", 16, QFont.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        w = fm.width(text) + 20
        h = fm.height() + 10
        
        x, y = 0, 0
        if self.corner_pos == 0: x, y = screen_geo.width() - w - margin, margin
        elif self.corner_pos == 1: x, y = screen_geo.width() - w - margin, screen_geo.height() - h - margin
        elif self.corner_pos == 2: x, y = margin, screen_geo.height() - h - margin
        elif self.corner_pos == 3: x, y = margin, margin

        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(QPen(QColor(0, 255, 0), 2))
        painter.drawRoundedRect(x, y, w, h, 5, 5)
        painter.setPen(QColor(0, 255, 0))
        painter.drawText(x + 10, y + h - 10, text)

    def draw_help(self, painter):
        screen_geo = self.rect()
        # WIDENED to 900px
        w, h = 900, 480 
        x, y = (screen_geo.width() - w) // 2, (screen_geo.height() - h) // 3

        painter.setBrush(QBrush(QColor(0, 0, 0, 230)))
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawRoundedRect(x, y, w, h, 10, 10)

        painter.setFont(QFont("Sans", 16, QFont.Bold))
        painter.setPen(QColor(0, 255, 0))
        painter.drawText(QRect(x, y + 20, w, 40), Qt.AlignCenter, "CONTROLS")

        commands = [
            ("Left Click", "Capture Coordinate"),
            ("Right Click", "Start/End Ruler Measurement"),
            ("Shift + Mouse", "Free-form Ruler (No Snap)"),
            ("E", "Toggle Edit Mode"),
            ("Space", "Cycle Coordinate Display Corner"),
            ("H", "Toggle this Help"),
            ("Q / Esc", "Quit Capture Mode")
        ]
        
        edit_commands = [
             ("Click Item", "Select (Edit Mode)"),
             ("Del", "Delete Selected"),
             ("R", "Rename Selected")
        ]

        painter.setFont(QFont("Monospace", 11))
        row_h = 30
        curr_y = y + 80
        # Adjusted column split for wider menu
        col_split = x + 350

        for cmd, desc in commands:
            painter.setPen(QColor(255, 255, 100))
            painter.drawText(x + 50, curr_y, cmd)
            painter.setPen(QColor(240, 240, 240))
            painter.drawText(col_split, curr_y, desc)
            curr_y += row_h
            
        curr_y += 10
        painter.setPen(QColor(0, 255, 255))
        painter.drawText(x + 50, curr_y, "--- Edit Mode Controls ---")
        curr_y += 30
        
        for cmd, desc in edit_commands:
            painter.setPen(QColor(0, 255, 255))
            painter.drawText(x + 50, curr_y, cmd)
            painter.setPen(QColor(240, 240, 240))
            painter.drawText(col_split, curr_y, desc)
            curr_y += row_h

        font = QFont("Sans", 10)
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(QRect(x, y + h - 30, w, 30), Qt.AlignCenter, "Press H to hide this menu")

    def draw_help_hint(self, painter):
        text = "Press H for Help"
        screen_geo = self.rect()
        painter.setFont(QFont("Sans", 10))
        fm = painter.fontMetrics()
        w, h = fm.width(text) + 20, fm.height() + 10
        x, y = (screen_geo.width() - w) // 2, screen_geo.height() - 50
        
        painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(x, y, w, h, 5, 5)
        painter.setPen(QColor(200, 200, 200))
        painter.drawText(QRect(x, y, w, h), Qt.AlignCenter, text)

    def draw_notifications(self, painter):
        now = datetime.now().timestamp()
        self.notifications = [n for n in self.notifications if n[1] > now]
        if not self.notifications: return

        painter.setFont(QFont("Sans", 12))
        fm = painter.fontMetrics()
        screen_geo = self.rect()
        start_y = 100 if self.corner_pos not in [0, 3] else 150
            
        for i, (text, _) in enumerate(self.notifications):
            w, h = fm.width(text) + 20, fm.height() + 10
            x, y = (screen_geo.width() - w) // 2, start_y + (i * (h + 5))
            
            painter.setBrush(QBrush(QColor(50, 50, 150, 200)))
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.drawRoundedRect(x, y, w, h, 5, 5)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRect(x, y, w, h), Qt.AlignCenter, text)

    def draw_text_with_bg(self, painter, text, x, y, color, bg_alpha=180):
        fm = painter.fontMetrics()
        w = fm.width(text) + 10
        h = fm.height() + 4
        painter.setBrush(QBrush(QColor(0, 0, 0, bg_alpha)))
        painter.setPen(Qt.NoPen)
        painter.drawRect(int(x - w/2), int(y - h/2 - 5), int(w), int(h))
        painter.setPen(color)
        painter.drawText(int(x - w/2 + 5), int(y + 5), text)

    def add_notification(self, text):
        self.notifications.append((text, datetime.now().timestamp() + 2))

    # --- Input Handling ---

    def mouseMoveEvent(self, event):
        self.cursor_pos = event.pos()

    def mousePressEvent(self, event):
        if self.capture_mode == "edit":
            if event.button() == Qt.LeftButton:
                self.select_nearest_item(event.pos())
            return

        if event.button() == Qt.LeftButton:
            if self.capture_mode == "normal":
                item = self.main_window.add_coordinate(self.cursor_pos.x(), self.cursor_pos.y())
                self.session_items.append((item, None)) # Store for edit mode
                self.add_notification(f"Captured: {self.cursor_pos.x()}, {self.cursor_pos.y()}")
            elif self.capture_mode == "ruler":
                self.finish_ruler(event.pos())

        elif event.button() == Qt.RightButton:
            if self.capture_mode == "normal":
                self.capture_mode = "ruler"
                self.ruler_start = event.pos()
                self.add_notification("Ruler Mode: Click to end")
            elif self.capture_mode == "ruler":
                self.finish_ruler(event.pos())

    def finish_ruler(self, end_pos):
        if not self.ruler_start: return
        start = self.ruler_start
        end = end_pos
        
        if not self.shift_pressed:
            dx = abs(end.x() - start.x())
            dy = abs(end.y() - start.y())
            if dx > dy * 10: end = QPoint(end.x(), start.y())
            elif dy > dx * 10: end = QPoint(start.x(), end.y())

        dist = math.sqrt((end.x() - start.x())**2 + (end.y() - start.y())**2)
        item = self.main_window.add_measurement(start.x(), start.y(), end.x(), end.y(), dist, (end != end_pos))
        self.session_items.append((item, None))
        
        self.add_notification(f"Measurement: {int(dist)}px")
        self.capture_mode = "normal"
        self.ruler_start = None

    def select_nearest_item(self, pos):
        limit = 20 # pixels detection radius
        closest_idx = -1
        min_dist = limit
        
        for i, (item, _) in enumerate(self.session_items):
            d = 1000
            if isinstance(item, CoordinateItem):
                d = math.sqrt((pos.x() - item.x)**2 + (pos.y() - item.y)**2)
            elif isinstance(item, MeasurementItem):
                # Calculate distance to line segment
                px, py = pos.x(), pos.y()
                x1, y1, x2, y2 = item.x1, item.y1, item.x2, item.y2
                
                # Line segment length squared
                l2 = (x1 - x2)**2 + (y1 - y2)**2
                if l2 == 0:
                    d = math.sqrt((px - x1)**2 + (py - y1)**2)
                else:
                    # Projection
                    t = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2
                    t = max(0, min(1, t))
                    proj_x = x1 + t * (x2 - x1)
                    proj_y = y1 + t * (y2 - y1)
                    d = math.sqrt((px - proj_x)**2 + (py - proj_y)**2)
            
            if d < min_dist:
                min_dist = d
                closest_idx = i
        
        self.selected_item_index = closest_idx

    def keyPressEvent(self, event):
        key = event.key()
        
        if key == Qt.Key_Shift:
            self.shift_pressed = True
        
        elif key == Qt.Key_E:
            if self.capture_mode == "edit":
                self.capture_mode = "normal"
                self.selected_item_index = -1
                self.add_notification("Exited Edit Mode")
            else:
                self.capture_mode = "edit"
                self.ruler_start = None
                self.add_notification("Edit Mode: Click item to select")
        
        elif key in [Qt.Key_Escape, Qt.Key_Q]:
            if self.capture_mode == "ruler":
                self.capture_mode = "normal"
                self.ruler_start = None
                self.add_notification("Ruler Cancelled")
            elif self.capture_mode == "edit":
                self.capture_mode = "normal"
                self.selected_item_index = -1
            else:
                self.close()
                self.main_window.show()
                
        elif key == Qt.Key_Space:
            self.corner_pos = (self.corner_pos + 1) % 4
            self.update()
        elif key == Qt.Key_H:
            self.show_help = not self.show_help
            self.update()
            
        # Edit Mode Actions
        if self.capture_mode == "edit" and self.selected_item_index != -1:
            if key == Qt.Key_Delete:
                self.delete_current_selection()
            elif key == Qt.Key_R:
                self.rename_current_selection()

    def delete_current_selection(self):
        item, _ = self.session_items[self.selected_item_index]
        if self.main_window.remove_item_by_reference(item):
            del self.session_items[self.selected_item_index]
            self.selected_item_index = -1
            self.add_notification("Item Deleted")

    def rename_current_selection(self):
        item, _ = self.session_items[self.selected_item_index]
        self.releaseKeyboard() # InputDialog needs keyboard
        text, ok = QInputDialog.getText(self, "Rename", "New Name:", text=item.name)
        self.grabKeyboard()
        
        if ok and text:
            # We must update the MainWindow tree which updates the model
            self.main_window.rename_item_by_reference(item, text)
            self.add_notification("Item Renamed")

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Shift:
            self.shift_pressed = False


# --- Main Application Window ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screen Coordinate Tool")
        self.resize(750, 650)
        self.data_store = DataStore()
        
        # Theme Setup
        self.dark_mode = False
        self.setup_ui()
        self.apply_theme() # Default to Light initially or preference

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top Bar
        top_layout = QHBoxLayout()
        self.capture_btn = QPushButton("Enter Screen Capture Mode")
        self.capture_btn.setMinimumHeight(80) # Made bigger
        self.capture_btn.setCursor(Qt.PointingHandCursor)
        self.capture_btn.clicked.connect(self.start_capture)
        
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setFixedSize(40, 40)
        self.theme_btn.clicked.connect(self.toggle_theme)
        
        top_layout.addWidget(self.capture_btn)
        top_layout.addWidget(self.theme_btn)
        layout.addLayout(top_layout)

        # 2. History Label
        self.history_label = QLabel("<b>History</b> (Drag to group, Double-click to rename, Del to remove)")
        self.history_label.setStyleSheet("font-size: 16px; margin-top: 10px;")
        layout.addWidget(self.history_label)

        # 3. Tree Widget
        self.tree = HistoryTreeWidget()
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_menu)
        
        # Key Shortcuts (Delete)
        self.shortcut_del = QApplication.instance().installEventFilter(self)

        layout.addWidget(self.tree)

        # 4. Footer Buttons
        btn_layout = QHBoxLayout()
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_all)
        self.btn_export = QPushButton("Export")
        self.btn_export.clicked.connect(self.export_data)
        self.btn_folder = QPushButton("New Folder")
        self.btn_folder.clicked.connect(self.add_folder)
        
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addWidget(self.btn_export)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_folder)
        layout.addLayout(btn_layout)

        # Load Data
        self.refresh_tree()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def apply_theme(self):
        app = QApplication.instance()
        
        if self.dark_mode:
            # Dark Palette
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.white)
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)
            app.setPalette(palette)
            
            # Tech Orange Gradient
            self.capture_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF5722, stop:1 #FF9800);
                    color: white; border-radius: 5px; font-weight: bold; font-size: 22px;
                }
                QPushButton:hover { background: #E64A19; }
            """)
            self.theme_btn.setText("☀️")
            
            # History Label White
            self.history_label.setStyleSheet("font-size: 16px; margin-top: 10px; color: white;")
            
        else:
            # Light (Default)
            app.setPalette(QApplication.style().standardPalette())
            
            # Blue Gradient
            self.capture_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2196F3, stop:1 #21CBF3);
                    color: white; border-radius: 5px; font-weight: bold; font-size: 22px;
                }
                QPushButton:hover { background: #1976D2; }
            """)
            self.theme_btn.setText("🌙")
            
            # History Label Black
            self.history_label.setStyleSheet("font-size: 16px; margin-top: 10px; color: black;")

    def eventFilter(self, source, event):
        if (event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete and 
            self.tree.hasFocus()):
            self.delete_selected()
            return True
        return super().eventFilter(source, event)

    def start_capture(self):
        self.hide()
        self.overlay = OverlayWindow(self)
        self.overlay.show()

    def add_coordinate(self, x, y):
        item = CoordinateItem(x, y)
        self.add_to_tree_root(item)
        self.save_data()
        return item

    def add_measurement(self, x1, y1, x2, y2, dist, auto_aligned):
        item = MeasurementItem(x1, y1, x2, y2, dist, auto_aligned=auto_aligned)
        self.add_to_tree_root(item)
        self.save_data()
        return item

    def add_to_tree_root(self, model_item):
        tree_item = self.create_tree_item(model_item)
        self.tree.addTopLevelItem(tree_item)
        self.tree.scrollToBottom()

    def add_folder(self):
        text, ok = QInputDialog.getText(self, "New Folder", "Folder Name:")
        if ok and text:
            folder = FolderItem(name=text)
            self.add_to_tree_root(folder)
            self.save_data()

    def create_tree_item(self, model_item):
        item = QTreeWidgetItem()
        item.setData(0, Qt.UserRole, model_item)
        
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable | 
                      Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
        
        if isinstance(model_item, FolderItem):
            item.setText(0, "📁 " + model_item.name)
            item.setText(1, f"{len(model_item.items)} items")
            item.setExpanded(model_item.expanded)
            
            # Make Folders Bold to distinguish them in the hierarchy
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            
            for child in model_item.items:
                child_tree_item = self.create_tree_item(child)
                item.addChild(child_tree_item)
                
        elif isinstance(model_item, CoordinateItem):
            item.setText(0, "📍 " + model_item.name)
            item.setText(1, f"({model_item.x}, {model_item.y})")
            
        elif isinstance(model_item, MeasurementItem):
            item.setText(0, "📏 " + model_item.name)
            detail = f"{int(model_item.distance)}px ({model_item.x1},{model_item.y1})→({model_item.x2},{model_item.y2})"
            if model_item.auto_aligned: detail += " [Aligned]"
            item.setText(1, detail)

        return item

    def refresh_tree(self):
        self.tree.clear()
        for item in self.data_store.root_items:
            self.tree.addTopLevelItem(self.create_tree_item(item))

    def save_data(self):
        self.data_store.save_from_tree(self.tree)

    def on_item_double_clicked(self, item, column):
        if column == 0:
            self.tree.editItem(item, 0)
    
    def on_item_changed(self, item, column):
        # Triggered when renaming is done
        self.save_data()

    def recalculate_folder_counts(self):
        """Recursively update folder item counts"""
        def process_item(item):
            data = item.data(0, Qt.UserRole)
            if isinstance(data, FolderItem):
                count = item.childCount()
                item.setText(1, f"{count} items")
                for i in range(count):
                    process_item(item.child(i))
                    
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            process_item(root.child(i))

    def open_menu(self, position):
        indexes = self.tree.selectedIndexes()
        if not indexes: return

        menu = QMenu()
        action_del = menu.addAction("Delete")
        action_grp = menu.addAction("Group into New Folder")
        
        action = menu.exec_(self.tree.viewport().mapToGlobal(position))
        
        if action == action_del:
            self.delete_selected()
        elif action == action_grp:
            self.group_selected()

    def delete_selected(self):
        root = self.tree.invisibleRootItem()
        for item in self.tree.selectedItems():
            (item.parent() or root).removeChild(item)
        
        self.recalculate_folder_counts()
        self.save_data()

    def remove_item_by_reference(self, model_item):
        """Helper for Overlay Edit Mode to delete items"""
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.UserRole) == model_item:
                (item.parent() or self.tree.invisibleRootItem()).removeChild(item)
                self.recalculate_folder_counts()
                self.save_data()
                return True
            iterator += 1
        return False

    def rename_item_by_reference(self, model_item, new_name):
        """Helper for Overlay Edit Mode to rename items"""
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.UserRole) == model_item:
                # Update Model
                model_item.name = new_name
                # Update UI (Respecting prefixes)
                prefix = ""
                if isinstance(model_item, CoordinateItem): prefix = "📍 "
                elif isinstance(model_item, MeasurementItem): prefix = "📏 "
                item.setText(0, prefix + new_name)
                self.save_data()
                return True
            iterator += 1
        return False

    def group_selected(self):
        items = self.tree.selectedItems()
        if not items: return
        
        text, ok = QInputDialog.getText(self, "Group", "Folder Name:")
        if not (ok and text): return
        
        folder_model = FolderItem(name=text)
        folder_tree_item = self.create_tree_item(folder_model)
        
        first_item = items[0]
        parent = first_item.parent() or self.tree.invisibleRootItem()
        index = parent.indexOfChild(first_item)
        
        parent.insertChild(index, folder_tree_item)
        
        for item in items:
            (item.parent() or self.tree.invisibleRootItem()).removeChild(item)
            folder_tree_item.addChild(item)
            
        folder_tree_item.setExpanded(True)
        self.recalculate_folder_counts()
        self.save_data()

    def clear_all(self):
        ret = QMessageBox.warning(self, "Clear All", "Delete all history?", 
                                  QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes:
            self.tree.clear()
            self.save_data()

    def export_data(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "coordinates.txt", "Text Files (*.txt)")
        if path:
            try:
                with open(path, 'w') as f:
                    f.write("Screen Coordinate Tool Export\n")
                    f.write("===========================\n\n")
                    self._export_recursive(f, self.tree.invisibleRootItem())
                QMessageBox.information(self, "Success", f"Saved to {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _export_recursive(self, f, parent_item, indent=""):
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            f.write(f"{indent}{item.text(0)} - {item.text(1)}\n")
            self._export_recursive(f, item, indent + "  ")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())
