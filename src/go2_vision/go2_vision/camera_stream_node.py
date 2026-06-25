#!/usr/bin/env python3
import sys

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class CameraStreamNode(Node):
    def __init__(self):
        super().__init__('camera_stream_node')

        self.cap = None
        self.udp_writer = None
        self.bridge = CvBridge()
        self.frame_size = (0, 0)
        self._consecutive_failures = 0

        try:
            self.declare_parameter('camera_path', '') #Cámara a la que se conectará el nodo
            self.declare_parameter(
                'backend_ip',
                '192.168.123.200',
            )  # IP del Backend
            self.declare_parameter('frame_id', 'front_camera_link')
            self.declare_parameter('max_failures', 60)  # ~2 s a 30 FPS

            # Puertos UDP
            self.declare_parameter('udp_port', 5000)
            self.declare_parameter('fps', 30)

            # Dimensiones para el Frontend
            self.declare_parameter('capture_width', 1280)
            self.declare_parameter('capture_height', 720)
            
            # Dimensiones para la IA
            self.declare_parameter('ai_width', 640)
            self.declare_parameter('ai_height', 640)

            self.camera_path = str(self.get_parameter('camera_path').value)
            self.backend_ip = str(self.get_parameter('backend_ip').value)
            self.udp_port = int(self.get_parameter('udp_port').value)
            self.fps = int(self.get_parameter('fps').value)
            self.capture_width = int(self.get_parameter('capture_width').value)
            self.capture_height = int(self.get_parameter('capture_height').value)
            self.ai_width = int(self.get_parameter('ai_width').value)
            self.ai_height = int(self.get_parameter('ai_height').value)
            self.frame_id = str(self.get_parameter('frame_id').value)
            self.max_failures = int(self.get_parameter('max_failures').value)

            self._validate_parameters()
            self._open_camera()
            self._create_udp_writer()

            self.image_publisher = self.create_publisher(
                Image,
                'camera/resized_640',
                qos_profile_sensor_data,
            )

            timer_period = 1.0 / float(self.fps)
            self.timer = self.create_timer(timer_period, self.timer_callback)
            self.get_logger().info(
                'Nodo listo.\n'
                f'Autopista A={"activa" if self._udp_writer_ready() else "deshabilitada"}.\n'
                f'Autopista B={self.image_publisher.topic_name}.\n'
                f'({self.ai_width}x{self.ai_height}), frame_id={self.frame_id}.'
            )
        except Exception:
            self.destroy_node()
            raise

    def _validate_parameters(self):
        if self.fps <= 0:
            raise ValueError('El parametro fps debe ser mayor a 0.')
        if self.capture_width <= 0 or self.capture_height <= 0:
            raise ValueError(
                'capture_width y capture_height deben ser mayores a 0.'
            )
        if self.ai_width <= 0 or self.ai_height <= 0:
            raise ValueError('ai_width y ai_height deben ser mayores a 0.')

    def _open_camera(self):
        self.get_logger().info(
            f'Abriendo {self.camera_path} con V4L2 '
            f'a {self.capture_width}x{self.capture_height} @ {self.fps} FPS.'
        )
        self.cap = cv2.VideoCapture(self.camera_path, cv2.CAP_V4L2)

        if not self.cap.isOpened():
            raise RuntimeError(
                f'No se pudo abrir {self.camera_path} con V4L2.'
            )

        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        camera_fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        self.frame_size = (frame_width, frame_height)

        self.get_logger().info(
            f'Captura confirmada a {frame_width}x{frame_height} @ {camera_fps:.2f} FPS.'
        )

    def _reopen_camera(self):
        self._consecutive_failures = 0
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        try:
            self._open_camera()
        except Exception as exc:
            self.get_logger().error(
                f'Reapertura fallida: {exc}', throttle_duration_sec=5.0
            )
            self.cap = None  # asegura el guard del timer


    def _create_udp_writer(self):
        frame_width, frame_height = self.frame_size
        gstreamer_pipeline = (
            'appsrc ! '
            'videoconvert ! video/x-raw,format=BGRx ! '
            'nvvidconv ! video/x-raw(memory:NVMM),format=NV12 ! '
            'nvv4l2h264enc insert-sps-pps=true bitrate=2000000 ! '
            'h264parse ! rtph264pay pt=96 ! '
            f'udpsink host={self.backend_ip} port={self.udp_port} sync=false'
        )

        self.udp_writer = cv2.VideoWriter(
            gstreamer_pipeline,
            cv2.CAP_GSTREAMER,
            0,
            float(self.fps),
            self.frame_size,
            True,
        )

        if self._udp_writer_ready():
            self.get_logger().info(
                f'Autopista A activa: UDP H.264 a {self.backend_ip}:{self.udp_port}.'
            )
            return

        self.get_logger().warning(
            'No se pudo iniciar el pipeline GStreamer para UDP. '
            'Se mantiene activa solo la publicacion ROS 2.'
        )

    def _udp_writer_ready(self):
        return self.udp_writer is not None and self.udp_writer.isOpened()

    def timer_callback(self):
        if self.cap is None:
            return

        ret, frame = self.cap.read()
        if not ret or frame is None:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.max_failures:
                self._reopen_camera()
            return
        self._consecutive_failures = 0

        if self._udp_writer_ready():
            self.udp_writer.write(frame)

        resized_frame = cv2.resize(
            frame,
            (self.ai_width, self.ai_height),
            interpolation=cv2.INTER_AREA,
        )
        msg = self.bridge.cv2_to_imgmsg(resized_frame, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        self.image_publisher.publish(msg)

    def destroy_node(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self.udp_writer is not None:
            self.udp_writer.release()
            self.udp_writer = None
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None

    try:
        node = CameraStreamNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'[camera_stream_node] Error al iniciar el nodo: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
