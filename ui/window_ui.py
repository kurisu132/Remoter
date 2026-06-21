"""
WindowUI — VLink 监控终端 UI 布局
纯 UI 构建：widget 创建、布局、样式表、信号连接。
不包含业务逻辑，所有回调通过 parent 提供。

用法：
    from ui.window_ui import WindowUI, GREEN, RED, GRAY, YELLOW
    WindowUI.setup_ui(self)   # self = QWidget 实例
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.video_opengl_widget import VideoOpenGLWidget
from stream.udp_control_sender import load_config

# ── 状态指示灯颜色（main_window 需要引用，故公开）──
GREEN  = "color: #22cc55; font-weight: bold;"
RED    = "color: #ff4444; font-weight: bold;"
GRAY   = "color: #666666; font-weight: bold;"
YELLOW = "color: #ffaa00; font-weight: bold;"

# ── 私有样式 ──
_CARD = (
    "background-color: #1e1e1e;"
    " border: 1px solid #2a2a2a;"
    " border-radius: 10px;"
)

_BTN_PTZ = """
    QPushButton {
        background-color: #2a2a2a; color: #ffffff;
        border: none; border-radius: 8px;
        font-size: 22px; font-weight: bold;
    }
    QPushButton:hover   { background-color: #3a3a3a; }
    QPushButton:pressed { background-color: #005599; }
"""

_BTN_STOP = """
    QPushButton {
        background-color: #7a2020; color: #ffffff;
        border: none; border-radius: 8px;
        font-size: 22px; font-weight: bold;
    }
    QPushButton:hover   { background-color: #9a3030; }
    QPushButton:pressed { background-color: #cc0000; }
"""

_BTN_LIGHT_ON = """
    QPushButton {
        background-color: #e8931a; color: #ffffff;
        border: none; border-radius: 8px;
        font-size: 16px; font-weight: bold;
    }
    QPushButton:hover   { background-color: #f0a030; }
    QPushButton:pressed { background-color: #c97a10; }
"""

_BTN_LIGHT_OFF = """
    QPushButton {
        background-color: #363636; color: #aaaaaa;
        border: none; border-radius: 8px;
        font-size: 16px; font-weight: bold;
    }
    QPushButton:hover   { background-color: #444444; }
    QPushButton:pressed { background-color: #555555; }
"""


class WindowUI:
    """纯 UI 构建器。

    调用 ``setup_ui(parent)`` 将所有 widget 作为属性挂载到 parent 上，
    并连接信号到 parent 的对应回调方法。
    """

    @staticmethod
    def setup_ui(parent: QWidget) -> None:
        _build_main(parent)

    # ── helpers (module-level) ──────────────────────────────────────────

    @staticmethod
    def _dot_label(name: str) -> QLabel:
        lbl = QLabel(f"● {name}")
        lbl.setStyleSheet(GRAY + " background-color: transparent;")
        return lbl

    @staticmethod
    def _section_title(icon: str, text: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background-color: transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        ic = QLabel(icon)
        ic.setStyleSheet("background-color: transparent; font-size: 14px;")
        h.addWidget(ic)
        lb = QLabel(text)
        lb.setStyleSheet(
            "background-color: transparent; color: #cccccc;"
            " font-size: 14px; font-weight: bold;"
        )
        h.addWidget(lb)
        h.addStretch()
        return row


# ──────────────────────────────────────────────────────────────────────
# 内部构建函数
# ──────────────────────────────────────────────────────────────────────

def _build_main(parent: QWidget) -> None:
    """顶层布局：背景 → 内容区 → 状态栏"""

    parent.setObjectName("MainWindow")
    parent.setStyleSheet("QWidget#MainWindow { background-color: #121212; }")

    root = QVBoxLayout(parent)
    root.setContentsMargins(8, 8, 8, 4)
    root.setSpacing(6)

    # ── 内容区（视频 + 右侧面板）──
    content = QWidget()
    content.setObjectName("contentArea")
    content.setStyleSheet("QWidget#contentArea { background-color: transparent; }")
    ch = QHBoxLayout(content)
    ch.setContentsMargins(0, 0, 6, 0)
    ch.setSpacing(0)

    parent.video_widget = VideoOpenGLWidget()
    parent.video_widget.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )
    ch.addWidget(parent.video_widget, stretch=1)
    ch.addWidget(_build_right_panel(parent))

    root.addWidget(content, stretch=1)

    # ── 状态栏 ──
    _build_status_bar(parent, root)


def _build_status_bar(parent: QWidget, root: QVBoxLayout) -> None:
    bar = QWidget()
    bar.setObjectName("statusBar")
    bar.setStyleSheet("QWidget#statusBar { background-color: transparent; }")
    bar.setFixedHeight(34)
    h = QHBoxLayout(bar)
    h.setContentsMargins(10, 0, 10, 0)
    h.setSpacing(0)

    parent._lbl_rtsp   = WindowUI._dot_label("RTSP")
    parent._lbl_stm32  = WindowUI._dot_label("STM32")
    parent._lbl_udp    = WindowUI._dot_label("UDP")
    parent._lbl_estop  = WindowUI._dot_label("ESTOP")
    parent._lbl_remote = WindowUI._dot_label("REMOTE")

    items = [
        parent._lbl_rtsp, parent._lbl_stm32, parent._lbl_udp,
        parent._lbl_estop, parent._lbl_remote,
    ]
    for i, w in enumerate(items):
        if i > 0:
            sep = QLabel("│")
            sep.setStyleSheet("color: #333333; padding: 0 8px;")
            h.addWidget(sep)
        h.addWidget(w)

    h.addStretch()

    lbl_ip = QLabel("目标 IP")
    lbl_ip.setStyleSheet("color: #777777; font-size: 12px;")
    h.addWidget(lbl_ip)

    cfg = load_config()
    parent._ip_edit = QLineEdit(cfg.get("target_ip", "192.168.1.11"))
    parent._ip_edit.setFixedWidth(130)
    parent._ip_edit.setFixedHeight(28)
    parent._ip_edit.setStyleSheet("""
        QLineEdit {
            background-color: #1e1e1e; color: #ffffff;
            border: 1px solid #3a3a3a; border-radius: 4px;
            padding: 2px 8px; font-size: 13px;
        }
        QLineEdit:focus { border-color: #005599; }
    """)
    h.addSpacing(8)
    h.addWidget(parent._ip_edit)

    btn = QPushButton("连接")
    btn.setFixedSize(56, 28)
    btn.setStyleSheet("""
        QPushButton {
            background-color: #005599; color: #ffffff;
            border: none; border-radius: 4px;
            font-size: 13px; font-weight: bold;
        }
        QPushButton:hover   { background-color: #0066bb; }
        QPushButton:pressed { background-color: #004488; }
    """)
    btn.clicked.connect(parent._on_connect)
    h.addSpacing(8)
    h.addWidget(btn)

    root.addWidget(bar)

    # UDP 状态刷新定时器
    parent._udp_ok_timer = QTimer(parent)
    parent._udp_ok_timer.setInterval(2000)
    parent._udp_ok_timer.timeout.connect(parent._refresh_udp_indicator)
    parent._udp_ok_timer.start()


# ──────────────────────────────────────────────────────────────────────
# 右侧面板
# ──────────────────────────────────────────────────────────────────────

def _build_right_panel(parent: QWidget) -> QWidget:
    panel = QWidget()
    panel.setObjectName("rightPanel")
    panel.setStyleSheet("QWidget#rightPanel { background-color: transparent; }")
    panel.setFixedWidth(280)
    v = QVBoxLayout(panel)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(8)

    v.addWidget(_build_light_card(parent))
    v.addWidget(_build_ptz_card(parent))
    v.addStretch()
    return panel


def _build_light_card(parent: QWidget) -> QWidget:
    card = QFrame()
    card.setObjectName("lightCard")
    card.setStyleSheet(f"QFrame#lightCard {{ {_CARD} }}")
    card.setFixedHeight(110)
    cv = QVBoxLayout(card)
    cv.setContentsMargins(16, 12, 16, 12)
    cv.setSpacing(10)

    cv.addWidget(WindowUI._section_title("💡", "补光灯"))

    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    parent._btn_light_on = QPushButton("  开灯  ")
    parent._btn_light_off = QPushButton("  关灯  ")
    parent._btn_light_on.setStyleSheet(_BTN_LIGHT_ON)
    parent._btn_light_off.setStyleSheet(_BTN_LIGHT_OFF)
    parent._btn_light_on.setFixedHeight(42)
    parent._btn_light_off.setFixedHeight(42)

    parent._btn_light_on.clicked.connect(parent._on_light_on)
    parent._btn_light_off.clicked.connect(parent._on_light_off)

    btn_row.addWidget(parent._btn_light_on)
    btn_row.addWidget(parent._btn_light_off)
    cv.addLayout(btn_row)
    return card


def _build_ptz_card(parent: QWidget) -> QWidget:
    card = QFrame()
    card.setObjectName("ptzCard")
    card.setStyleSheet(f"QFrame#ptzCard {{ {_CARD} }}")
    cv = QVBoxLayout(card)
    cv.setContentsMargins(16, 12, 16, 16)
    cv.setSpacing(10)

    cv.addWidget(WindowUI._section_title("🎯", "云台控制"))

    grid = QGridLayout()
    grid.setSpacing(8)

    parent._btn_up    = QPushButton("▲")
    parent._btn_down  = QPushButton("▼")
    parent._btn_left  = QPushButton("◀")
    parent._btn_right = QPushButton("▶")
    parent._btn_stop  = QPushButton("■")

    for b in (parent._btn_up, parent._btn_down, parent._btn_left, parent._btn_right):
        b.setStyleSheet(_BTN_PTZ)
        b.setMinimumSize(68, 56)
        b.setFixedHeight(56)

    parent._btn_stop.setStyleSheet(_BTN_STOP)
    parent._btn_stop.setMinimumSize(68, 56)
    parent._btn_stop.setFixedHeight(56)

    grid.addWidget(parent._btn_up,    0, 1)
    grid.addWidget(parent._btn_left,  1, 0)
    grid.addWidget(parent._btn_stop,  1, 1)
    grid.addWidget(parent._btn_right, 1, 2)
    grid.addWidget(parent._btn_down,  2, 1)

    cv.addLayout(grid)

    # ── 方向键事件 ──
    parent._btn_up.pressed.connect(lambda p=parent: p._ptz_move("up"))
    parent._btn_up.released.connect(parent._ptz_stop)
    parent._btn_down.pressed.connect(lambda p=parent: p._ptz_move("down"))
    parent._btn_down.released.connect(parent._ptz_stop)
    parent._btn_left.pressed.connect(lambda p=parent: p._ptz_move("left"))
    parent._btn_left.released.connect(parent._ptz_stop)
    parent._btn_right.pressed.connect(lambda p=parent: p._ptz_move("right"))
    parent._btn_right.released.connect(parent._ptz_stop)
    parent._btn_stop.clicked.connect(parent._ptz_stop)

    return card
