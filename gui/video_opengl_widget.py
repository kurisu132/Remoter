"""
VideoOpenGLWidget - OpenGL 硬件加速视频渲染控件
完整修复版：解决所有已知问题（错误检查器、Y轴翻转、强制重绘、内存安全）
修复：PySide6 导入路径兼容性问题
优化：移除帧数统计日志，适配 5MP 分辨率
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

    5MP 优化版本特性：
    - ✅ 兼容多个 PySide6 版本的导入路径
    - ✅ 彻底禁用 PyOpenGL 错误检查器
    - ✅ 修复纹理坐标 Y 轴翻转问题
    - ✅ 使用 repaint() 强制立即重绘
    - ✅ 内存安全的 QImage 处理
    - ✅ 移除周期性帧数日志（更清爽的输出）
    - ✅ 支持 5MP (2592x1904) 高分辨率渲染
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.texture_id = None
        self.shader_program = None
        self.vbo_vertices = None
        self.vbo_tex_coords = None
        self.current_frame = None
        self.frame_count = 0
        self.frame_width = 0
        self.frame_height = 0
        logger.info("✅ VideoOpenGLWidget (5MP 优化版) 初始化完成")

    def initializeGL(self):
        """初始化 OpenGL 环境"""
        try:
            logger.info("🎨 开始初始化 OpenGL 环境...")

            # 清屏颜色
            glClearColor(0.0, 0.0, 0.0, 1.0)

            # 创建纹理
            self.texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glBindTexture(GL_TEXTURE_2D, 0)

            # 编译着色器
            self.shader_program = self._compile_shaders()

            # 创建 VBO
            self._create_vbo()

            logger.info("✅ OpenGL 初始化成功（纹理、着色器、VBO 已就绪）")

        except Exception as e:
            logger.error(f"❌ initializeGL 失败: {e}", exc_info=True)

    def _compile_shaders(self):
        """编译顶点和片段着色器"""
        # 顶点着色器
        vertex_shader_source = """
        #version 330 core
        layout(location = 0) in vec2 position;
        layout(location = 1) in vec2 texCoord;
        out vec2 vTexCoord;
        void main() {
            gl_Position = vec4(position, 0.0, 1.0);
            vTexCoord = texCoord;
        }
        """

        # 片段着色器
        fragment_shader_source = """
        #version 330 core
        in vec2 vTexCoord;
        out vec4 fragColor;
        uniform sampler2D videoTexture;
        void main() {
            fragColor = texture(videoTexture, vTexCoord);
        }
        """

        # 编译顶点着色器
        vertex_shader = glCreateShader(GL_VERTEX_SHADER)
        glShaderSource(vertex_shader, vertex_shader_source)
        glCompileShader(vertex_shader)
        if not glGetShaderiv(vertex_shader, GL_COMPILE_STATUS):
            error = glGetShaderInfoLog(vertex_shader).decode()
            logger.error(f"❌ 顶点着色器编译失败: {error}")
            raise RuntimeError("顶点着色器编译失败")

        # 编译片段着色器
        fragment_shader = glCreateShader(GL_FRAGMENT_SHADER)
        glShaderSource(fragment_shader, fragment_shader_source)
        glCompileShader(fragment_shader)
        if not glGetShaderiv(fragment_shader, GL_COMPILE_STATUS):
            error = glGetShaderInfoLog(fragment_shader).decode()
            logger.error(f"❌ 片段着色器编译失败: {error}")
            raise RuntimeError("片段着色器编译失败")

        # 链接着色器程序
        shader_program = glCreateProgram()
        glAttachShader(shader_program, vertex_shader)
        glAttachShader(shader_program, fragment_shader)
        glLinkProgram(shader_program)
        if not glGetProgramiv(shader_program, GL_LINK_STATUS):
            error = glGetProgramInfoLog(shader_program).decode()
            logger.error(f"❌ 着色器程序链接失败: {error}")
            raise RuntimeError("着色器程序链接失败")

        # 删除独立的着色器对象
        glDeleteShader(vertex_shader)
        glDeleteShader(fragment_shader)

        logger.info("✅ 着色器编译成功")
        return shader_program

    def _create_vbo(self):
        """创建顶点缓冲对象（VBO）"""
        # 顶点坐标（NDC，左下角为原点）
        vertices = np.array([
            -1.0, -1.0,  # 左下
             1.0, -1.0,  # 右下
             1.0,  1.0,  # 右上
            -1.0, -1.0,  # 左下
             1.0,  1.0,  # 右上
            -1.0,  1.0   # 左上
        ], dtype=np.float32)

        # ✅ 关键修复4：纹理坐标 Y 轴翻转
        # OpenGL 纹理坐标：左下角 (0,0)，右上角 (1,1)
        # QImage 坐标：左上角 (0,0)，右下角 (w,h)
        # 需要翻转 Y 坐标：屏幕底部对应 V=1.0，屏幕顶部对应 V=0.0
        tex_coords = np.array([
            0.0, 1.0,  # 左下 → QImage 左上
            1.0, 1.0,  # 右下 → QImage 右上
            1.0, 0.0,  # 右上 → QImage 右下
            0.0, 1.0,  # 左下 → QImage 左上
            1.0, 0.0,  # 右上 → QImage 右下
            0.0, 0.0   # 左上 → QImage 左下
        ], dtype=np.float32)

        # 创建 VBO
        self.vbo_vertices = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_vertices)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        self.vbo_tex_coords = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_tex_coords)
        glBufferData(GL_ARRAY_BUFFER, tex_coords.nbytes, tex_coords, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        logger.info("✅ VBO 创建成功（纹理坐标已修复 Y 轴翻转）")

    def resizeGL(self, w, h):
        """窗口尺寸变化时调用"""
        glViewport(0, 0, w, h)
        logger.info(f"🔄 OpenGL 视口调整: {w}x{h}")

    def paintGL(self):
        """渲染函数"""
        try:
            # 清屏
            glClear(GL_COLOR_BUFFER_BIT)

            # 如果没有帧数据，跳过
            if self.current_frame is None:
                return

            # 绑定纹理和着色器
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glUseProgram(self.shader_program)

            # 绑定顶点 VBO
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_vertices)
            glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(0)

            # 绑定纹理坐标 VBO
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_tex_coords)
            glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 0, None)
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

            # ✅ 移除周期性帧数日志（不再显示"已渲染多少帧"）

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
            # 记录尺寸变化（仅首次或尺寸改变时输出）
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

            # ✅ 移除周期性纹理数据统计日志

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

            if self.vbo_vertices:
                glDeleteBuffers(1, [self.vbo_vertices])

            if self.vbo_tex_coords:
                glDeleteBuffers(1, [self.vbo_tex_coords])

            self.doneCurrent()
            logger.info("✅ OpenGL 资源清理完成")

        except Exception as e:
            logger.error(f"❌ cleanup 异常: {e}", exc_info=True)
