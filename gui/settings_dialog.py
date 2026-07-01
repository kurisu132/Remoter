"""
SettingsDialog — VLink 配置对话框

显示并编辑 config.toml 中的所有可配置项：
  - 摄像头：主机地址、用户名、密码
  - 串口：STM32 串口路径
  - UDP 控制：目标 IP、目标端口

保存时调用 save_config_values()，写回 config.toml（保留注释）。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from stream.udp_control_sender import load_config, save_config_values

_DIALOG_STYLE = """
    QDialog {
        background-color: #1a1a1a;
    }
    QLabel {
        color: #cccccc;
        font-size: 13px;
        background-color: transparent;
    }
    QLineEdit {
        background-color: #2a2a2a;
        color: #ffffff;
        border: 1px solid #3a3a3a;
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 13px;
    }
    QLineEdit:focus {
        border-color: #005599;
    }
    QPushButton {
        background-color: #2a2a2a;
        color: #cccccc;
        border: 1px solid #3a3a3a;
        border-radius: 4px;
        padding: 6px 18px;
        font-size: 13px;
    }
    QPushButton:hover { background-color: #3a3a3a; }
    QPushButton:pressed { background-color: #1e1e1e; }
    QPushButton[text="保存"] {
        background-color: #005599;
        color: #ffffff;
        border: none;
    }
    QPushButton[text="保存"]:hover { background-color: #0066bb; }
    QPushButton[text="保存"]:pressed { background-color: #004488; }
"""

_SECTION_STYLE = (
    "color: #888888; font-size: 11px; font-weight: bold;"
    " background-color: transparent; padding-top: 6px;"
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VLink 设置")
        self.setMinimumWidth(360)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        cfg = load_config()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        # ── 摄像头 ──
        layout.addWidget(self._section("摄像头"))
        form_cam = QFormLayout()
        form_cam.setSpacing(8)
        form_cam.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._camera_host = QLineEdit(cfg.get("camera_host", "192.168.1.36"))
        self._camera_user = QLineEdit(cfg.get("camera_user", "admin"))
        self._camera_pass = QLineEdit(cfg.get("camera_pass", ""))
        self._camera_pass.setEchoMode(QLineEdit.EchoMode.Password)

        form_cam.addRow("主机地址", self._camera_host)
        form_cam.addRow("用户名",   self._camera_user)
        form_cam.addRow("密码",     self._camera_pass)
        layout.addLayout(form_cam)

        # ── 串口 ──
        layout.addWidget(self._section("串口"))
        form_serial = QFormLayout()
        form_serial.setSpacing(8)
        form_serial.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._stm32_port = QLineEdit(cfg.get("stm32_port", "/dev/ttyACM0"))
        self._stm32_port.setPlaceholderText("Linux: /dev/ttyACM0  |  Windows: COM3")
        form_serial.addRow("串口路径", self._stm32_port)
        layout.addLayout(form_serial)

        # ── UDP 控制 ──
        layout.addWidget(self._section("UDP 控制"))
        form_udp = QFormLayout()
        form_udp.setSpacing(8)
        form_udp.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._target_ip   = QLineEdit(cfg.get("target_ip", "192.168.1.11"))
        self._target_port = QLineEdit(str(cfg.get("target_port", 9000)))
        self._target_port.setFixedWidth(80)

        form_udp.addRow("目标 IP",   self._target_ip)
        form_udp.addRow("目标端口",  self._target_port)
        layout.addLayout(form_udp)

        layout.addSpacing(8)

        # ── 按钮行 ──
        buttons = QDialogButtonBox()
        btn_cancel = buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        btn_save   = buttons.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_cancel.clicked.connect(self.reject)
        btn_save.clicked.connect(self._on_save)
        layout.addWidget(buttons)

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(_SECTION_STYLE)
        return lbl

    def _on_save(self):
        port_text = self._target_port.text().strip()
        try:
            port = int(port_text)
        except ValueError:
            port = 9000

        save_config_values({
            "camera_host": self._camera_host.text().strip(),
            "camera_user": self._camera_user.text().strip(),
            "camera_pass": self._camera_pass.text(),
            "stm32_port":  self._stm32_port.text().strip(),
            "target_ip":   self._target_ip.text().strip(),
            "target_port": port,
        })
        self.accept()
