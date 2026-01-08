# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'window.ui'
##
## Created by: Qt User Interface Compiler version 6.8.0
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
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QSizePolicy, QVBoxLayout,
    QWidget)

from gui.video_opengl_widget import VideoOpenGLWidget

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
        self.video_widget = VideoOpenGLWidget(Camera)
        self.video_widget.setObjectName(u"video_widget")
        self.video_widget.setMinimumSize(QSize(640, 480))
        self.video_widget.setStyleSheet(u"border: 2px solid black;  /* 2\u50cf\u7d20\u5bbd\uff0c\u7ea2\u8272\u5b9e\u7ebf\u8fb9\u6846 */\n"
"border-radius: 10px;     /* \u53ef\u9009\uff1a\u5706\u89d2\u8fb9\u6846 */\n"
"padding: 3px;           /* \u53ef\u9009\uff1a\u5185\u8fb9\u8ddd */")

        self.verticalLayout_4.addWidget(self.video_widget)


        self.horizontalLayout_3.addLayout(self.verticalLayout_4)

        self.horizontalLayout_3.setStretch(1, 4)

        self.retranslateUi(Camera)

        QMetaObject.connectSlotsByName(Camera)
    # setupUi

    def retranslateUi(self, Camera):
        Camera.setWindowTitle(QCoreApplication.translate("Camera", u"Form", None))
    # retranslateUi

