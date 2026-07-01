"""
VideoOpenGLWidget - OpenGL 硬件加速视频渲染控件

输入格式：NV12（YUV 4:2:0，h264_rkmpp 硬件解码原生格式）
渲染方式：Y 平面 + UV 平面分别上传为两个纹理，GLSL Shader 做 BT.601 YUV→RGB 转换。
好处：跳过 swscaler，消除 I 帧 100-200ms 卡顿；管道数据量减半（7.4 MB vs 14.8 MB）。

支持 OpenGL 3.3 Core Profile（x86/桌面）和 OpenGL ES 3.0（ARM/Mali-G610）双模式。
initializeGL 内通过 context().isOpenGLES() 自动选择对应 GLSL 版本，无需外部配置。
"""
import logging
import time
import numpy as np

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *

import OpenGL
OpenGL.ERROR_CHECKING = False
OpenGL.ERROR_LOGGING = False
OpenGL.ERROR_ON_COPY = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VideoOpenGLWidget")


class VideoOpenGLWidget(QOpenGLWidget):
    # ---------- GLSL 3.3 Core (x86 桌面) ----------
    _VERT_DESKTOP = """
    #version 330 core
    layout(location = 0) in vec2 position;
    layout(location = 1) in vec2 texCoord;
    out vec2 vTexCoord;
    void main() {
        gl_Position = vec4(position, 0.0, 1.0);
        vTexCoord = texCoord;
    }
    """
    _FRAG_DESKTOP = """
    #version 330 core
    in vec2 vTexCoord;
    out vec4 fragColor;
    uniform sampler2D yTexture;
    uniform sampler2D uvTexture;
    void main() {
        float y  = texture(yTexture,  vTexCoord).r;
        float cb = texture(uvTexture, vTexCoord).r - 0.5;
        float cr = texture(uvTexture, vTexCoord).g - 0.5;
        float r = clamp(y + 1.402  * cr,              0.0, 1.0);
        float g = clamp(y - 0.3441 * cb - 0.7141 * cr, 0.0, 1.0);
        float b = clamp(y + 1.772  * cb,              0.0, 1.0);
        fragColor = vec4(r, g, b, 1.0);
    }
    """

    # ---------- GLSL 300 es (ARM/Mali-G610 + Panfrost) ----------
    _VERT_ES = """
    #version 300 es
    layout(location = 0) in vec2 position;
    layout(location = 1) in vec2 texCoord;
    out vec2 vTexCoord;
    void main() {
        gl_Position = vec4(position, 0.0, 1.0);
        vTexCoord = texCoord;
    }
    """
    _FRAG_ES = """
    #version 300 es
    precision mediump float;
    in vec2 vTexCoord;
    out vec4 fragColor;
    uniform sampler2D yTexture;
    uniform sampler2D uvTexture;
    void main() {
        float y  = texture(yTexture,  vTexCoord).r;
        float cb = texture(uvTexture, vTexCoord).r - 0.5;
        float cr = texture(uvTexture, vTexCoord).g - 0.5;
        float r = clamp(y + 1.402  * cr,              0.0, 1.0);
        float g = clamp(y - 0.3441 * cb - 0.7141 * cr, 0.0, 1.0);
        float b = clamp(y + 1.772  * cb,              0.0, 1.0);
        fragColor = vec4(r, g, b, 1.0);
    }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_es = False
        self.y_texture_id  = None   # Y 平面（亮度），GL_RED
        self.uv_texture_id = None   # UV 平面（色度），GL_RG，width/2 × height/2
        self.shader_program = None
        self.vao = None
        self.vbo_vertices = None
        self.vbo_tex_coords = None
        self._pending_frame = None   # (data: bytes, width: int, height: int) 或 None
        self._has_frame = False      # 是否已收到过至少一帧
        self.frame_count = 0
        self._upload_count = 0
        self.frame_width = 0
        self.frame_height = 0
        logger.info("VideoOpenGLWidget initialized")

    def initializeGL(self):
        try:
            self._is_es = self.context().isOpenGLES()
            mode = "OpenGL ES 3.0" if self._is_es else "OpenGL 3.3 Desktop"
            logger.info(f"OpenGL context: {mode}")

            glClearColor(0.0, 0.0, 0.0, 1.0)

            self.y_texture_id  = glGenTextures(1)
            self.uv_texture_id = glGenTextures(1)
            for tex_id in (self.y_texture_id, self.uv_texture_id):
                glBindTexture(GL_TEXTURE_2D, tex_id)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glBindTexture(GL_TEXTURE_2D, 0)

            self.vao = glGenVertexArrays(1)
            self.shader_program = self._compile_shaders()
            self._create_vbo()

            logger.info("OpenGL initialized (Y/UV textures / VAO / shader / VBO ready)")

        except Exception as e:
            logger.error(f"initializeGL failed: {e}", exc_info=True)

    def _compile_shaders(self):
        vert_src = self._VERT_ES if self._is_es else self._VERT_DESKTOP
        frag_src = self._FRAG_ES if self._is_es else self._FRAG_DESKTOP

        vertex_shader = glCreateShader(GL_VERTEX_SHADER)
        glShaderSource(vertex_shader, vert_src)
        glCompileShader(vertex_shader)
        if not glGetShaderiv(vertex_shader, GL_COMPILE_STATUS):
            error = glGetShaderInfoLog(vertex_shader).decode()
            logger.error(f"vertex shader compile error: {error}")
            raise RuntimeError("vertex shader compile failed")

        fragment_shader = glCreateShader(GL_FRAGMENT_SHADER)
        glShaderSource(fragment_shader, frag_src)
        glCompileShader(fragment_shader)
        if not glGetShaderiv(fragment_shader, GL_COMPILE_STATUS):
            error = glGetShaderInfoLog(fragment_shader).decode()
            logger.error(f"fragment shader compile error: {error}")
            raise RuntimeError("fragment shader compile failed")

        shader_program = glCreateProgram()
        glAttachShader(shader_program, vertex_shader)
        glAttachShader(shader_program, fragment_shader)
        glLinkProgram(shader_program)
        if not glGetProgramiv(shader_program, GL_LINK_STATUS):
            error = glGetProgramInfoLog(shader_program).decode()
            logger.error(f"shader link error: {error}")
            raise RuntimeError("shader link failed")

        glDeleteShader(vertex_shader)
        glDeleteShader(fragment_shader)

        logger.info("shaders compiled successfully")
        return shader_program

    def _create_vbo(self):
        glBindVertexArray(self.vao)

        vertices = np.array([
            -1.0, -1.0,
             1.0, -1.0,
             1.0,  1.0,
            -1.0,  1.0
        ], dtype=np.float32)

        tex_coords = np.array([
            0.0, 1.0,
            1.0, 1.0,
            1.0, 0.0,
            0.0, 0.0
        ], dtype=np.float32)

        self.vbo_vertices = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_vertices)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(0)

        self.vbo_tex_coords = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_tex_coords)
        glBufferData(GL_ARRAY_BUFFER, tex_coords.nbytes, tex_coords, GL_STATIC_DRAW)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(1)

        glBindVertexArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        logger.info("VBO created and bound to VAO")

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

    def paintGL(self):
        try:
            # 消费最新待上传帧（若无新帧则复用已上传纹理）
            if self._pending_frame is not None:
                data, width, height = self._pending_frame
                self._pending_frame = None

                y_size  = width * height
                y_arr   = np.frombuffer(data[:y_size], dtype=np.uint8)
                uv_arr  = np.frombuffer(data[y_size:], dtype=np.uint8)

                t0 = time.monotonic()

                glBindTexture(GL_TEXTURE_2D, self.y_texture_id)
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RED, width, height, 0,
                             GL_RED, GL_UNSIGNED_BYTE, y_arr)

                glBindTexture(GL_TEXTURE_2D, self.uv_texture_id)
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RG, width // 2, height // 2, 0,
                             GL_RG, GL_UNSIGNED_BYTE, uv_arr)

                glBindTexture(GL_TEXTURE_2D, 0)
                self._has_frame = True

                self._upload_count += 1
                if self._upload_count % 30 == 0:
                    logger.info(
                        f"[gl] upload={self._upload_count}  "
                        f"texUpload={(time.monotonic()-t0)*1000:.1f}ms"
                    )

            glClear(GL_COLOR_BUFFER_BIT)

            if not self._has_frame:
                return

            prog = self.shader_program
            glUseProgram(prog)

            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.y_texture_id)
            glUniform1i(glGetUniformLocation(prog, "yTexture"), 0)

            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, self.uv_texture_id)
            glUniform1i(glGetUniformLocation(prog, "uvTexture"), 1)

            glBindVertexArray(self.vao)
            glDrawArrays(GL_TRIANGLE_FAN, 0, 4)
            glBindVertexArray(0)

            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, 0)
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, 0)
            glUseProgram(0)

            self.frame_count += 1

        except Exception as e:
            if "GLError" not in str(type(e).__name__):
                logger.error(f"paintGL 异常: {e}", exc_info=True)

    def update_frame(self, data: bytes, width: int, height: int):
        """接收新 NV12 帧：仅存储最新帧，由 paintGL 统一消费。
        不在此处做 GL 上传——避免 makeCurrent/repaint 阻塞主线程导致帧积压。"""
        if self.y_texture_id is None or not data:
            return
        if self.frame_width != width or self.frame_height != height:
            self.frame_width = width
            self.frame_height = height
            logger.info(f"视频尺寸: {width}x{height}")
        self._pending_frame = (data, width, height)   # 旧帧直接丢弃，始终保留最新
        self.update()                                  # Qt 自动合并多次 update()

    def cleanup(self):
        try:
            self.makeCurrent()

            if self.y_texture_id is not None:
                glDeleteTextures([self.y_texture_id])
                self.y_texture_id = None

            if self.uv_texture_id is not None:
                glDeleteTextures([self.uv_texture_id])
                self.uv_texture_id = None

            if self.shader_program is not None:
                glDeleteProgram(self.shader_program)
                self.shader_program = None

            if self.vbo_vertices is not None:
                glDeleteBuffers(1, [self.vbo_vertices])
                self.vbo_vertices = None

            if self.vbo_tex_coords is not None:
                glDeleteBuffers(1, [self.vbo_tex_coords])
                self.vbo_tex_coords = None

            if self.vao is not None:
                glDeleteVertexArrays(1, [self.vao])
                self.vao = None

            self.doneCurrent()
            logger.info("OpenGL 资源清理完成")

        except Exception as e:
            logger.error(f"cleanup 异常: {e}", exc_info=True)
