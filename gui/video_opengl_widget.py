"""
OpenGL硬件加速视频渲染组件（方案C）
使用GPU渲染纹理，接收FFmpeg软解码的QImage
"""

import logging
import numpy as np
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import QOpenGLShaderProgram, QOpenGLShader, QOpenGLTexture
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImage, QSurfaceFormat
from OpenGL import GL

logger = logging.getLogger("VideoOpenGLWidget")


class VideoOpenGLWidget(QOpenGLWidget):
    """
    OpenGL视频渲染控件

    功能：
    1. 接收QImage格式的视频帧
    2. 转换为OpenGL纹理
    3. 使用GPU渲染到屏幕

    优势：
    - GPU加速缩放和过滤
    - 消除QPixmap的CPU开销
    - 保持与FFmpegRTSPPlayer的兼容性
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # OpenGL资源
        self.shader_program = None
        self.texture = None
        self.vao = None
        self.vbo = None

        # 视频帧数据
        self.current_image = None
        self.video_width = 1280
        self.video_height = 720

        # 设置OpenGL表面格式
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        self.setFormat(fmt)

        logger.info("VideoOpenGLWidget 初始化完成")

    def minimumSizeHint(self):
        """最小尺寸"""
        return QSize(640, 480)

    def sizeHint(self):
        """建议尺寸"""
        return QSize(1280, 720)

    def initializeGL(self):
        """初始化OpenGL上下文（仅调用一次）"""
        logger.info("开始初始化OpenGL上下文")

        # 创建Shader程序
        self._create_shader_program()

        # 创建纹理对象
        self._create_texture()

        # 创建顶点缓冲
        self._create_vertex_buffer()

        # 设置OpenGL状态
        GL.glClearColor(0.0, 0.0, 0.0, 1.0)
        GL.glDisable(GL.GL_DEPTH_TEST)

        logger.info("OpenGL上下文初始化成功")

    def _create_shader_program(self):
        """创建Shader程序"""
        self.shader_program = QOpenGLShaderProgram(self)

        # 顶点着色器（定义屏幕空间四边形）
        vertex_shader = """
        #version 330 core
        layout(location = 0) in vec2 position;
        layout(location = 1) in vec2 texCoord;
        out vec2 TexCoord;
        
        void main()
        {
            gl_Position = vec4(position, 0.0, 1.0);
            TexCoord = texCoord;
        }
        """

        # 片段着色器（纹理采样）
        fragment_shader = """
        #version 330 core
        in vec2 TexCoord;
        out vec4 FragColor;
        uniform sampler2D videoTexture;
        
        void main()
        {
            FragColor = texture(videoTexture, TexCoord);
        }
        """

        # 编译着色器
        if not self.shader_program.addShaderFromSourceCode(
            QOpenGLShader.Vertex, vertex_shader
        ):
            logger.error(f"顶点着色器编译失败: {self.shader_program.log()}")
            return

        if not self.shader_program.addShaderFromSourceCode(
            QOpenGLShader.Fragment, fragment_shader
        ):
            logger.error(f"片段着色器编译失败: {self.shader_program.log()}")
            return

        # 链接程序
        if not self.shader_program.link():
            logger.error(f"Shader程序链接失败: {self.shader_program.log()}")
            return

        logger.info("Shader程序创建成功")

    def _create_texture(self):
        """创建OpenGL纹理对象"""
        self.texture = QOpenGLTexture(QOpenGLTexture.Target2D)
        self.texture.create()
        self.texture.bind()

        # 设置纹理参数（线性过滤，性能更好）
        self.texture.setMinificationFilter(QOpenGLTexture.Linear)
        self.texture.setMagnificationFilter(QOpenGLTexture.Linear)
        self.texture.setWrapMode(QOpenGLTexture.ClampToEdge)

        logger.info("OpenGL纹理对象创建成功")

    def _create_vertex_buffer(self):
        """创建顶点缓冲对象（全屏四边形）"""
        # 顶点数据：位置(x,y) + 纹理坐标(u,v)
        vertices = np.array([
            # 位置        纹理坐标
            -1.0, -1.0,  0.0, 1.0,  # 左下
             1.0, -1.0,  1.0, 1.0,  # 右下
             1.0,  1.0,  1.0, 0.0,  # 右上
            -1.0,  1.0,  0.0, 0.0   # 左上
        ], dtype=np.float32)

        # 创建VAO和VBO
        self.vao = GL.glGenVertexArrays(1)
        self.vbo = GL.glGenBuffers(1)

        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(
            GL.GL_ARRAY_BUFFER,
            vertices.nbytes,
            vertices,
            GL.GL_STATIC_DRAW
        )

        # 位置属性（location=0）
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, None)
        GL.glEnableVertexAttribArray(0)

        # 纹理坐标属性（location=1）
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, GL.ctypes.c_void_p(8))
        GL.glEnableVertexAttribArray(1)

        GL.glBindVertexArray(0)
        logger.info("顶点缓冲对象创建成功")

    def paintGL(self):
        """渲染帧（每次update()调用）"""
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        if self.current_image is None:
            return

        # 上传纹理到GPU
        self._upload_texture(self.current_image)

        # 使用Shader程序
        self.shader_program.bind()

        # 绑定纹理
        GL.glActiveTexture(GL.GL_TEXTURE0)
        self.texture.bind()
        self.shader_program.setUniformValue("videoTexture", 0)

        # 绘制四边形
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)
        GL.glBindVertexArray(0)

        self.shader_program.release()

    def _upload_texture(self, q_image: QImage):
        """上传QImage到OpenGL纹理"""
        # 转换为OpenGL兼容格式
        img = q_image.convertToFormat(QImage.Format_RGB888)

        # 获取图像数据
        width = img.width()
        height = img.height()
        ptr = img.bits()

        # 上传到GPU
        self.texture.bind()
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D,
            0,
            GL.GL_RGB,
            width,
            height,
            0,
            GL.GL_RGB,
            GL.GL_UNSIGNED_BYTE,
            ptr
        )

    def resizeGL(self, w, h):
        """窗口大小变化"""
        GL.glViewport(0, 0, w, h)
        logger.info(f"OpenGL视口调整: {w}x{h}")

    def update_frame(self, q_image: QImage):
        """
        更新视频帧（从FFmpegRTSPPlayer调用）

        Args:
            q_image: QImage格式的视频帧
        """
        self.current_image = q_image
        self.video_width = q_image.width()
        self.video_height = q_image.height()
        self.update()  # 触发paintGL()重绘

    def cleanup(self):
        """清理OpenGL资源"""
        if self.texture:
            self.texture.destroy()
        if self.vao:
            GL.glDeleteVertexArrays(1, [self.vao])
        if self.vbo:
            GL.glDeleteBuffers(1, [self.vbo])
        if self.shader_program:
            self.shader_program.removeAllShaders()
        logger.info("OpenGL资源已清理")
