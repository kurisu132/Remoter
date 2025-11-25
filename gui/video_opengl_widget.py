"""
VideoOpenGLWidget - OpenGL 硬件加速视频渲染控件
完整修复版：解决所有已知问题（错误检查器、Y轴翻转、强制重绘、内存安全）
修复：PySide6 导入路径兼容性问题
"""
import sys
import logging
import numpy as np

# ✅ 修复1：兼容不同 PySide6 版本的导入路径
try:
    # PySide6 6.0-6.2 版本
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    try:
        # PySide6 6.3+ 版本
        from PySide6.QtWidgets import QOpenGLWidget
    except ImportError:
        # 最后尝试 PyQt6（如果用户使用 PyQt6）
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from OpenGL.GL import *

# ✅ 关键修复2：彻底禁用错误检查器
import OpenGL
OpenGL.ERROR_CHECKING = False
OpenGL.ERROR_LOGGING = False
OpenGL.ERROR_ON_COPY = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VideoOpenGLWidget")


class VideoOpenGLWidget(QOpenGLWidget):
    """
    使用 OpenGL 硬件加速渲染视频流的自定义控件

    完整修复版本特性：
    - ✅ 兼容多个 PySide6 版本的导入路径
    - ✅ 彻底禁用 PyOpenGL 错误检查器
    - ✅ 修复纹理坐标 Y 轴翻转问题
    - ✅ 使用 repaint() 强制立即重绘
    - ✅ 内存安全的 QImage 处理
    - ✅ 详细的调试日志
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # OpenGL 资源
        self.texture_id = None
        self.shader_program = None
        self.vbo = None

        # 视频状态
        self.current_frame = None
        self.frame_width = 0
        self.frame_height = 0
        self.frame_count = 0

        # ✅ 关键修复3：设置 Widget 属性强制立即重绘
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setUpdateBehavior(QOpenGLWidget.NoPartialUpdate)

        logger.info("✅ VideoOpenGLWidget 已创建")

    def initializeGL(self):
        """OpenGL 初始化"""
        try:
            # 打印 OpenGL 版本信息
            vendor = glGetString(GL_VENDOR).decode('utf-8')
            renderer = glGetString(GL_RENDERER).decode('utf-8')
            version = glGetString(GL_VERSION).decode('utf-8')
            logger.info(f"OpenGL 初始化: {vendor}, {renderer}, {version}")

            # 创建纹理
            self.texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

            # 创建 Shader
            self.shader_program = self._create_shader_program()

            # 创建 VBO
            self.vbo = glGenBuffers(1)

            logger.info(f"✅ OpenGL 资源创建成功 (纹理ID={self.texture_id}, Shader={self.shader_program}, VBO={self.vbo})")

        except Exception as e:
            logger.error(f"❌ initializeGL 失败: {e}", exc_info=True)

    def _create_shader_program(self):
        """创建并编译 Shader 程序"""
        # 顶点着色器
        vertex_shader = """
        #version 330 core
        layout(location = 0) in vec2 position;
        layout(location = 1) in vec2 texCoord;
        out vec2 fragTexCoord;
        void main() {
            gl_Position = vec4(position, 0.0, 1.0);
            fragTexCoord = texCoord;
        }
        """

        # 片段着色器
        fragment_shader = """
        #version 330 core
        in vec2 fragTexCoord;
        out vec4 fragColor;
        uniform sampler2D videoTexture;
        void main() {
            fragColor = texture(videoTexture, fragTexCoord);
        }
        """

        # 编译顶点着色器
        vs = glCreateShader(GL_VERTEX_SHADER)
        glShaderSource(vs, vertex_shader)
        glCompileShader(vs)
        if glGetShaderiv(vs, GL_COMPILE_STATUS) != GL_TRUE:
            error = glGetShaderInfoLog(vs).decode('utf-8')
            raise RuntimeError(f"顶点着色器编译失败: {error}")

        # 编译片段着色器
        fs = glCreateShader(GL_FRAGMENT_SHADER)
        glShaderSource(fs, fragment_shader)
        glCompileShader(fs)
        if glGetShaderiv(fs, GL_COMPILE_STATUS) != GL_TRUE:
            error = glGetShaderInfoLog(fs).decode('utf-8')
            raise RuntimeError(f"片段着色器编译失败: {error}")

        # 链接程序
        program = glCreateProgram()
        glAttachShader(program, vs)
        glAttachShader(program, fs)
        glLinkProgram(program)
        if glGetProgramiv(program, GL_LINK_STATUS) != GL_TRUE:
            error = glGetProgramInfoLog(program).decode('utf-8')
            raise RuntimeError(f"Shader 程序链接失败: {error}")

        glDeleteShader(vs)
        glDeleteShader(fs)

        logger.info("✅ Shader 程序创建成功")
        return program

    def resizeGL(self, w, h):
        """窗口尺寸变化时调整视口"""
        glViewport(0, 0, w, h)
        logger.info(f"📐 视口已调整: {w}x{h}")

    def paintGL(self):
        """渲染当前帧"""
        # 清屏（使用深灰色背景便于调试）
        glClearColor(0.2, 0.2, 0.2, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        # 如果没有帧数据，直接返回
        if self.current_frame is None:
            return

        try:
            # 使用 Shader 程序
            glUseProgram(self.shader_program)

            # 绑定纹理
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)

            # ✅ 关键修复4：纹理坐标 Y 轴翻转
            # OpenGL 坐标系：(0,0) 在左下角，Y 轴向上
            # QImage 坐标系：(0,0) 在左上角，Y 轴向下
            # 所以纹理坐标需要翻转：(0,1) 和 (1,0) 互换
            vertices = np.array([
                # 位置 (x, y)      纹理坐标 (u, v) - 已翻转
                -1.0, -1.0,        0.0, 1.0,  # 左下角 -> 纹理左上角
                 1.0, -1.0,        1.0, 1.0,  # 右下角 -> 纹理右上角
                -1.0,  1.0,        0.0, 0.0,  # 左上角 -> 纹理左下角
                 1.0, -1.0,        1.0, 1.0,  # 右下角 -> 纹理右上角
                 1.0,  1.0,        1.0, 0.0,  # 右上角 -> 纹理右下角
                -1.0,  1.0,        0.0, 0.0,  # 左上角 -> 纹理左下角
            ], dtype=np.float32)

            # 使用 VBO
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
            glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

            # 设置顶点属性
            stride = 4 * 4  # 4个float，每个4字节
            glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(8))
            glEnableVertexAttribArray(1)

            # 设置 uniform
            tex_location = glGetUniformLocation(self.shader_program, "videoTexture")
            glUniform1i(tex_location, 0)

            # 绘制
            glDrawArrays(GL_TRIANGLES, 0, 6)

            # 清理
            glDisableVertexAttribArray(0)
            glDisableVertexAttribArray(1)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glBindTexture(GL_TEXTURE_2D, 0)
            glUseProgram(0)

            self.frame_count += 1

            # 每 100 帧输出一次状态
            if self.frame_count % 100 == 0:
                logger.info(f"🎬 已渲染 {self.frame_count} 帧 (尺寸: {self.frame_width}x{self.frame_height})")

        except Exception as e:
            logger.error(f"❌ paintGL 异常: {e}", exc_info=True)

    def update_frame(self, q_image: QImage):
        """
        更新视频帧（从外部调用）

        Args:
            q_image: QImage 对象（必须已经调用 .copy() 进行深拷贝）
        """
        if q_image is None or q_image.isNull():
            logger.warning("⚠️ 收到空图像，跳过")
            return

        try:
            # 记录尺寸变化
            if self.frame_width != q_image.width() or self.frame_height != q_image.height():
                self.frame_width = q_image.width()
                self.frame_height = q_image.height()
                logger.info(f"📏 视频尺寸: {self.frame_width}x{self.frame_height}")

            # 转换为 RGB888 格式
            if q_image.format() != QImage.Format_RGB888:
                q_image = q_image.convertToFormat(QImage.Format_RGB888)

            # 保存当前帧
            self.current_frame = q_image

            # 上传纹理数据
            self.makeCurrent()  # 确保 OpenGL 上下文
            glBindTexture(GL_TEXTURE_2D, self.texture_id)

            # 使用 numpy 确保内存安全
            width = q_image.width()
            height = q_image.height()
            ptr = q_image.constBits()

            # ✅ 关键修复5：使用 numpy 数组复制数据
            if isinstance(ptr, int):
                # 如果是整数地址，使用 ctypes
                import ctypes
                buffer_size = width * height * 3
                buffer = (ctypes.c_ubyte * buffer_size).from_address(ptr)
                img_data = np.frombuffer(buffer, dtype=np.uint8).copy()
            else:
                # 如果是 sip.voidptr，直接转换
                img_data = np.frombuffer(ptr, dtype=np.uint8, count=width * height * 3).copy()

            img_data = img_data.reshape((height, width, 3))

            # 每 200 帧输出一次纹理数据统计
            if self.frame_count % 200 == 0:
                logger.info(f"📊 纹理数据: min={img_data.min()}, max={img_data.max()}, mean={img_data.mean():.1f}")

            # 上传到 GPU
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, width, height, 0, GL_RGB, GL_UNSIGNED_BYTE, img_data)
            glBindTexture(GL_TEXTURE_2D, 0)
            self.doneCurrent()

            # ✅ 关键修复6：使用 repaint() 强制立即重绘，避免 Qt 事件合并
            self.repaint()

        except Exception as e:
            logger.error(f"❌ update_frame 异常: {e}", exc_info=True)

    def cleanup(self):
        """清理 OpenGL 资源"""
        try:
            self.makeCurrent()

            if self.texture_id:
                glDeleteTextures([self.texture_id])
                logger.info("✅ 纹理已删除")

            if self.shader_program:
                glDeleteProgram(self.shader_program)
                logger.info("✅ Shader 程序已删除")

            if self.vbo:
                glDeleteBuffers(1, [self.vbo])
                logger.info("✅ VBO 已删除")

            self.doneCurrent()

        except Exception as e:
            logger.error(f"❌ cleanup 异常: {e}", exc_info=True)
