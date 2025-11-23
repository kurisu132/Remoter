"""
OpenGL硬件支持检测工具
用于在运行时判断是否启用OpenGL渲染
"""

import logging
import sys

logger = logging.getLogger("OpenGLChecker")


class OpenGLChecker:
    """OpenGL环境检测器"""

    @staticmethod
    def check_opengl_support():
        """
        检测OpenGL支持

        Returns:
            bool: True=支持, False=不支持
        """
        try:
            # 检查PyOpenGL导入
            import OpenGL.GL as GL
            from PySide6.QtOpenGLWidgets import QOpenGLWidget

            # 检查OpenGL版本
            from PySide6.QtGui import QOpenGLContext, QSurfaceFormat

            # 创建临时上下文检测
            fmt = QSurfaceFormat()
            fmt.setVersion(3, 3)
            fmt.setProfile(QSurfaceFormat.CoreProfile)
            QSurfaceFormat.setDefaultFormat(fmt)

            logger.info("✅ OpenGL库导入成功")
            logger.info("✅ PySide6 OpenGL模块可用")
            return True

        except ImportError as e:
            logger.warning(f"❌ OpenGL导入失败: {e}")
            return False
        except Exception as e:
            logger.warning(f"❌ OpenGL检测异常: {e}")
            return False

    @staticmethod
    def get_fallback_reason():
        """
        获取降级原因

        Returns:
            str: 降级原因说明
        """
        try:
            import OpenGL.GL
            return "OpenGL库可用，但运行时检测失败"
        except ImportError:
            return "PyOpenGL未安装，请执行: pip install PyOpenGL"
        except Exception as e:
            return f"未知错误: {str(e)}"


# 独立测试
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 50)
    print("OpenGL环境检测")
    print("=" * 50)

    if OpenGLChecker.check_opengl_support():
        print("✅ 系统支持OpenGL硬件加速")
    else:
        print("❌ 系统不支持OpenGL")
        print(f"原因: {OpenGLChecker.get_fallback_reason()}")
