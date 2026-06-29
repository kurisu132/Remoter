"""
VideoOpenGLWidget - OpenGL 硬件加速视频渲染控件
支持 OpenGL 3.3 Core Profile（x86/桌面）和 OpenGL ES 3.0（ARM/Mali-G610）双模式。
initializeGL 内通过 context().isOpenGLES() 自动选择对应 GLSL 版本，无需外部配置。
"""
import logging
import time
import numpy as np

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QImage
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
    uniform sampler2D videoTexture;
    void main() {
        fragColor = texture(videoTexture, vTexCoord);
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
    uniform sampler2D videoTexture;
    void main() {
        fragColor = texture(videoTexture, vTexCoord);
    }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_es = False
        self.texture_id = None
        self.shader_program = None
        self.vao = None
        self.vbo_vertices = None
        self.vbo_tex_coords = None
        self.current_frame = None
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

            self.texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glBindTexture(GL_TEXTURE_2D, 0)

            self.vao = glGenVertexArrays(1)
            self.shader_program = self._compile_shaders()
            self._create_vbo()

            logger.info("OpenGL initialized (texture / VAO / shader / VBO ready)")

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
            glClear(GL_COLOR_BUFFER_BIT)

            if self.current_frame is None:
                return

            glUseProgram(self.shader_program)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)

            tex_location = glGetUniformLocation(self.shader_program, "videoTexture")
            glUniform1i(tex_location, 0)

            glBindVertexArray(self.vao)
            glDrawArrays(GL_TRIANGLE_FAN, 0, 4)
            glBindVertexArray(0)

            glBindTexture(GL_TEXTURE_2D, 0)
            glUseProgram(0)

            self.frame_count += 1

        except Exception as e:
            if "GLError" not in str(type(e).__name__):
                logger.error(f"paintGL 异常: {e}", exc_info=True)

    def update_frame(self, q_image: QImage):
        if self.texture_id is None or q_image is None or q_image.isNull():
            return

        if q_image.format() != QImage.Format_RGB888:
            q_image = q_image.convertToFormat(QImage.Format_RGB888)

        if self.frame_width != q_image.width() or self.frame_height != q_image.height():
            self.frame_width = q_image.width()
            self.frame_height = q_image.height()
            logger.info(f"视频尺寸: {self.frame_width}x{self.frame_height}")

        self.current_frame = q_image

        try:
            t0 = time.monotonic()
            self.makeCurrent()
            t1 = time.monotonic()

            glBindTexture(GL_TEXTURE_2D, self.texture_id)

            width, height = q_image.width(), q_image.height()
            ptr = q_image.constBits()
            if isinstance(ptr, int):
                import ctypes
                buf = (ctypes.c_ubyte * (width * height * 3)).from_address(ptr)
                img_data = np.frombuffer(buf, dtype=np.uint8).copy()
            else:
                img_data = np.frombuffer(ptr, dtype=np.uint8, count=width * height * 3).copy()

            img_data = img_data.reshape((height, width, 3))
            t2 = time.monotonic()
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, width, height, 0,
                         GL_RGB, GL_UNSIGNED_BYTE, img_data)
            t3 = time.monotonic()

            glBindTexture(GL_TEXTURE_2D, 0)
            self.doneCurrent()

            self._upload_count += 1
            if self._upload_count % 30 == 0:
                logger.info(
                    f"[gl] upload={self._upload_count}  "
                    f"makeCurrent={( t1-t0)*1000:.1f}ms  "
                    f"numpy={(t2-t1)*1000:.1f}ms  "
                    f"texUpload={(t3-t2)*1000:.1f}ms  "
                    f"total={(t3-t0)*1000:.1f}ms"
                )

            self.repaint()

        except Exception as e:
            logger.error(f"update_frame 异常: {e}", exc_info=True)

    def cleanup(self):
        try:
            self.makeCurrent()

            if self.texture_id is not None:
                glDeleteTextures([self.texture_id])
                self.texture_id = None

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
