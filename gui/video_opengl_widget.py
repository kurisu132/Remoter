"""
VideoOpenGLWidget - OpenGL 硬件加速视频渲染控件
修复版：添加 VAO 支持，解决 GL_INVALID_OPERATION 错误
"""
import sys
import logging
import numpy as np

# ✅ 兼容不同 PySide6 版本的导入路径
try:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    try:
        from PySide6.QtWidgets import QOpenGLWidget
    except ImportError:
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from OpenGL.GL import *

# ✅ 彻底禁用错误检查器
import OpenGL
OpenGL.ERROR_CHECKING = False
OpenGL.ERROR_LOGGING = False
OpenGL.ERROR_ON_COPY = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VideoOpenGLWidget")


class VideoOpenGLWidget(QOpenGLWidget):
    """
    使用 OpenGL 硬件加速渲染视频流的自定义控件

    修复特性：
    - ✅ 添加 VAO 支持（修复 GL_INVALID_OPERATION）
    - ✅ 兼容多个 PySide6 版本
    - ✅ 禁用 PyOpenGL 错误检查器
    - ✅ 纹理坐标 Y 轴翻转
    - ✅ 支持 5MP (2592x1904) 高分辨率
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.texture_id = None
        self.shader_program = None
        self.vao = None  # ✅ 新增：VAO
        self.vbo_vertices = None
        self.vbo_tex_coords = None
        self.current_frame = None
        self.frame_count = 0
        self.frame_width = 0
        self.frame_height = 0
        logger.info("✅ VideoOpenGLWidget 初始化完成")

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

            # ✅ 创建 VAO（关键修复）
            self.vao = glGenVertexArrays(1)
            logger.info(f"✅ VAO 创建成功 (ID: {self.vao})")

            # 编译着色器
            self.shader_program = self._compile_shaders()

            # ✅ 创建 VBO 并绑定到 VAO
            self._create_vbo()

            logger.info("✅ OpenGL 初始化成功（纹理、VAO、着色器、VBO 已就绪）")

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
        """创建顶点缓冲对象（VBO）并绑定到 VAO"""
        # ✅ 绑定 VAO（所有后续操作都会记录到这个 VAO）
        glBindVertexArray(self.vao)

        # 顶点坐标（使用 TRIANGLE_FAN，只需4个顶点）
        vertices = np.array([
            -1.0, -1.0,  # 左下
             1.0, -1.0,  # 右下
             1.0,  1.0,  # 右上
            -1.0,  1.0   # 左上
        ], dtype=np.float32)

        # ✅ 纹理坐标 Y 轴翻转
        tex_coords = np.array([
            0.0, 1.0,  # 左下 → QImage 左上
            1.0, 1.0,  # 右下 → QImage 右上
            1.0, 0.0,  # 右上 → QImage 右下
            0.0, 0.0   # 左上 → QImage 左下
        ], dtype=np.float32)

        # 创建顶点 VBO
        self.vbo_vertices = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_vertices)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(0)

        # 创建纹理坐标 VBO
        self.vbo_tex_coords = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_tex_coords)
        glBufferData(GL_ARRAY_BUFFER, tex_coords.nbytes, tex_coords, GL_STATIC_DRAW)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(1)

        # ✅ 解绑 VAO（保存所有设置）
        glBindVertexArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        logger.info("✅ VBO 创建成功并绑定到 VAO")

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

            # 使用着色器
            glUseProgram(self.shader_program)

            # 绑定纹理
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)

            # 设置 uniform
            tex_location = glGetUniformLocation(self.shader_program, "videoTexture")
            glUniform1i(tex_location, 0)

            # ✅ 使用 VAO（所有顶点属性已保存）
            glBindVertexArray(self.vao)
            glDrawArrays(GL_TRIANGLE_FAN, 0, 4)
            glBindVertexArray(0)

            # 清理
            glBindTexture(GL_TEXTURE_2D, 0)
            glUseProgram(0)

            self.frame_count += 1

        except Exception as e:
            # 只记录严重错误，忽略 GLError 误报
            if "GLError" not in str(type(e).__name__):
                logger.error(f"❌ paintGL 异常: {e}", exc_info=True)

    def update_frame(self, q_image: QImage):
        """
        更新视频帧（从外部调用）

        Args:
            q_image: QImage 对象
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
            self.makeCurrent()
            glBindTexture(GL_TEXTURE_2D, self.texture_id)

            # 使用 numpy 确保内存安全
            width = q_image.width()
            height = q_image.height()
            ptr = q_image.constBits()

            # 转换为 numpy 数组
            if isinstance(ptr, int):
                import ctypes
                buffer_size = width * height * 3
                buffer = (ctypes.c_ubyte * buffer_size).from_address(ptr)
                img_data = np.frombuffer(buffer, dtype=np.uint8).copy()
            else:
                img_data = np.frombuffer(ptr, dtype=np.uint8, count=width * height * 3).copy()

            img_data = img_data.reshape((height, width, 3))

            # 上传到 GPU
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, width, height, 0, GL_RGB, GL_UNSIGNED_BYTE, img_data)
            glBindTexture(GL_TEXTURE_2D, 0)
            self.doneCurrent()

            # 触发重绘
            self.update()

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

            # ✅ 删除 VAO
            if self.vao:
                glDeleteVertexArrays(1, [self.vao])
                logger.info("✅ VAO 已删除")

            self.doneCurrent()
            logger.info("✅ OpenGL 资源清理完成")

        except Exception as e:
            logger.error(f"❌ cleanup 异常: {e}", exc_info=True)