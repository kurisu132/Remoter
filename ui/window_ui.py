# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'window.ui'
##
## Created by: Qt User Interface Compiler version 6.9.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

class Ui_Camera(object):
    def setupUi(self, Camera):
        if not Camera.objectName():
            Camera.setObjectName(u"Camera")
        Camera.resize(859, 500)
        self.horizontalLayout_3 = QHBoxLayout(Camera)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.openGLWidget = QOpenGLWidget(Camera)
        self.openGLWidget.setObjectName(u"openGLWidget")

        self.horizontalLayout_3.addWidget(self.openGLWidget)

        self.verticalLayout_4 = QVBoxLayout()
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.video_label = QLabel(Camera)
        self.video_label.setObjectName(u"video_label")
        self.video_label.setMinimumSize(QSize(640, 480))
        self.video_label.setStyleSheet(u"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 10px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */")

        self.verticalLayout_4.addWidget(self.video_label)


        self.horizontalLayout_3.addLayout(self.verticalLayout_4)

        self.verticalLayout_3 = QVBoxLayout()
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.horizontalSpacer_4 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_4.addItem(self.horizontalSpacer_4)

        self.fullscreen = QPushButton(Camera)
        self.fullscreen.setObjectName(u"fullscreen")
        self.fullscreen.setStyleSheet(u"font: 20pt \"Minion Pro\";\n"
"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 5px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */\n"
"")

        self.horizontalLayout_4.addWidget(self.fullscreen)

        self.horizontalSpacer_7 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_4.addItem(self.horizontalSpacer_7)

        self.horizontalLayout_4.setStretch(0, 1)
        self.horizontalLayout_4.setStretch(1, 3)
        self.horizontalLayout_4.setStretch(2, 1)

        self.verticalLayout_3.addLayout(self.horizontalLayout_4)

        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.horizontalSpacer_5 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_5.addItem(self.horizontalSpacer_5)

        self.autho = QPushButton(Camera)
        self.autho.setObjectName(u"autho")
        self.autho.setStyleSheet(u"font: 20pt \"Minion Pro\";\n"
"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 5px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */\n"
"")

        self.horizontalLayout_5.addWidget(self.autho)

        self.horizontalSpacer_6 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_5.addItem(self.horizontalSpacer_6)

        self.horizontalLayout_5.setStretch(0, 1)
        self.horizontalLayout_5.setStretch(1, 3)
        self.horizontalLayout_5.setStretch(2, 1)

        self.verticalLayout_3.addLayout(self.horizontalLayout_5)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_3.addItem(self.verticalSpacer)

        self.label = QLabel(Camera)
        self.label.setObjectName(u"label")
        self.label.setStyleSheet(u"font: 15pt \"Minion Pro\";\n"
"\n"
"")

        self.verticalLayout_3.addWidget(self.label)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer_2)

        self.open = QPushButton(Camera)
        self.open.setObjectName(u"open")
        self.open.setStyleSheet(u"font: 20pt \"Minion Pro\";\n"
"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 5px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */\n"
"")

        self.horizontalLayout_2.addWidget(self.open)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer)

        self.close = QPushButton(Camera)
        self.close.setObjectName(u"close")
        self.close.setStyleSheet(u"font: 20pt \"Minion Pro\";\n"
"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 5px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */\n"
"")

        self.horizontalLayout_2.addWidget(self.close)

        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer_3)

        self.horizontalLayout_2.setStretch(0, 1)
        self.horizontalLayout_2.setStretch(1, 2)
        self.horizontalLayout_2.setStretch(2, 1)
        self.horizontalLayout_2.setStretch(3, 2)
        self.horizontalLayout_2.setStretch(4, 1)

        self.verticalLayout_3.addLayout(self.horizontalLayout_2)

        self.verticalSpacer_2 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_3.addItem(self.verticalSpacer_2)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.verticalLayout_5 = QVBoxLayout()
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.verticalSpacer_3 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_5.addItem(self.verticalSpacer_3)

        self.left = QPushButton(Camera)
        self.left.setObjectName(u"left")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.left.sizePolicy().hasHeightForWidth())
        self.left.setSizePolicy(sizePolicy)
        self.left.setStyleSheet(u"font: 20pt \"Minion Pro\";\n"
"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 5px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */\n"
"")

        self.verticalLayout_5.addWidget(self.left)

        self.verticalSpacer_4 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_5.addItem(self.verticalSpacer_4)

        self.verticalLayout_5.setStretch(0, 1)
        self.verticalLayout_5.setStretch(1, 1)
        self.verticalLayout_5.setStretch(2, 1)

        self.horizontalLayout.addLayout(self.verticalLayout_5)

        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.up = QPushButton(Camera)
        self.up.setObjectName(u"up")
        sizePolicy.setHeightForWidth(self.up.sizePolicy().hasHeightForWidth())
        self.up.setSizePolicy(sizePolicy)
        self.up.setStyleSheet(u"font: 20pt \"Minion Pro\";\n"
"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 5px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */\n"
"")

        self.verticalLayout_2.addWidget(self.up)

        self.verticalSpacer_7 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_2.addItem(self.verticalSpacer_7)

        self.down = QPushButton(Camera)
        self.down.setObjectName(u"down")
        sizePolicy.setHeightForWidth(self.down.sizePolicy().hasHeightForWidth())
        self.down.setSizePolicy(sizePolicy)
        self.down.setStyleSheet(u"font: 20pt \"Minion Pro\";\n"
"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 5px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */\n"
"")

        self.verticalLayout_2.addWidget(self.down)

        self.verticalLayout_2.setStretch(0, 1)
        self.verticalLayout_2.setStretch(1, 1)
        self.verticalLayout_2.setStretch(2, 1)

        self.horizontalLayout.addLayout(self.verticalLayout_2)

        self.verticalLayout_6 = QVBoxLayout()
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.verticalSpacer_6 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_6.addItem(self.verticalSpacer_6)

        self.right = QPushButton(Camera)
        self.right.setObjectName(u"right")
        sizePolicy.setHeightForWidth(self.right.sizePolicy().hasHeightForWidth())
        self.right.setSizePolicy(sizePolicy)
        self.right.setStyleSheet(u"font: 20pt \"Minion Pro\";\n"
"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 5px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */\n"
"")

        self.verticalLayout_6.addWidget(self.right)

        self.verticalSpacer_5 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_6.addItem(self.verticalSpacer_5)

        self.verticalLayout_6.setStretch(0, 1)
        self.verticalLayout_6.setStretch(1, 1)
        self.verticalLayout_6.setStretch(2, 1)

        self.horizontalLayout.addLayout(self.verticalLayout_6)

        self.horizontalLayout.setStretch(0, 1)
        self.horizontalLayout.setStretch(1, 1)
        self.horizontalLayout.setStretch(2, 1)

        self.verticalLayout_3.addLayout(self.horizontalLayout)

        self.verticalLayout_3.setStretch(2, 1)
        self.verticalLayout_3.setStretch(3, 2)
        self.verticalLayout_3.setStretch(4, 1)
        self.verticalLayout_3.setStretch(5, 1)
        self.verticalLayout_3.setStretch(6, 3)

        self.horizontalLayout_3.addLayout(self.verticalLayout_3)

        self.horizontalLayout_3.setStretch(1, 4)
        self.horizontalLayout_3.setStretch(2, 1)

        self.retranslateUi(Camera)

        QMetaObject.connectSlotsByName(Camera)
    # setupUi

    def retranslateUi(self, Camera):
        Camera.setWindowTitle(QCoreApplication.translate("Camera", u"Form", None))
        self.video_label.setText("")
        self.fullscreen.setText(QCoreApplication.translate("Camera", u"\u5168\u5c4f", None))
        self.autho.setText(QCoreApplication.translate("Camera", u"\u8ba4\u8bc1", None))
        self.label.setText(QCoreApplication.translate("Camera", u"\u8865\u5149\u706f", None))
        self.open.setText(QCoreApplication.translate("Camera", u"\u5f00", None))
        self.close.setText(QCoreApplication.translate("Camera", u"\u5173", None))
        self.left.setText(QCoreApplication.translate("Camera", u"\u2190", None))
        self.up.setText(QCoreApplication.translate("Camera", u"\u2191", None))
        self.down.setText(QCoreApplication.translate("Camera", u"\u2193", None))
        self.right.setText(QCoreApplication.translate("Camera", u"\u2192", None))
    # retranslateUi

