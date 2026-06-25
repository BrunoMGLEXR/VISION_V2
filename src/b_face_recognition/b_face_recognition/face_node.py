#!/usr/bin/env python3

# =================================================================
# EL ORDEN DORADO (ANTÍDOTO TLS PARA ARM64 Y JETSON)
# Estas 3 importaciones DEBEN ir antes de rclpy para reservar la 
# memoria estática (TLS) y evitar el Segmentation Fault de libgomp.
import cv2
import sklearn
from insightface.app import FaceAnalysis
# =================================================================

# Librerías para ROS2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vigilance_interfaces.msg import AlarmReport
from rclpy.qos import qos_profile_sensor_data
from ament_index_python.packages import get_package_share_directory


# === INICIO DEL PARCHE EDGE AI (JETSON) ===
# Engañamos a la librería albumentations inyectando los atributos de OpenCV 4.5+ 
# en nuestro OpenCV 4.1 nativo para que InsightFace no colapse al importarse.
if not hasattr(cv2, 'INTER_NEAREST_EXACT'):
    cv2.INTER_NEAREST_EXACT = cv2.INTER_NEAREST
if not hasattr(cv2, 'INTER_LINEAR_EXACT'):
    cv2.INTER_LINEAR_EXACT = cv2.INTER_LINEAR
# === FIN DEL PARCHE ==

import numpy as np
import os
import time
from collections import deque

# ================= CONFIGURACIÓN FINAL =================
ARCHIVO_DB = 'backup_facial.npz'
MODELO_INSIGHTFACE = 'buffalo_m'

BURST_SIZE = 5
AREA_MINIMA = 5000
ASPECT_RATIO_MIN = 0.5
ASPECT_RATIO_MAX = 1.5
UMBRAL_ENTRADA = 0.70
UMBRAL_SALIDA = 0.65

INFER_EVERY_N_FRAMES = 5
LOG_INFERENCE_EVERY = 10
TRT_CACHE_DIR = '/root/.insightface/trt_cache'
# =======================================================

def normalizar_vector(embedding):
    embedding = np.array(embedding)
    norm = np.linalg.norm(embedding)
    if norm == 0: return embedding
    return embedding / norm

def cargar_embeddings(db_path):
    if not os.path.exists(db_path):
        return None, None
    data = np.load(db_path)
    return data['embeddings'], data['names']

def area_rostro(face):
    x1, y1, x2, y2 = face.bbox
    return max(0, x2 - x1) * max(0, y2 - y1)

class FaceRecognitionNode(Node):
    def __init__(self):
        super().__init__('face_recognition_node')
        self.get_logger().info('Nodo FaceRecognitionNode creado (Modo Edge AI Puro)')

        self.declare_parameter('camera_topic', '/front/camera/resized_640')
        self.declare_parameter('show_debug_window', True) 
        
        camera_topic = self.get_parameter('camera_topic').value
        self.show_debug = self.get_parameter('show_debug_window').value

        self.known_embeddings = None
        self.known_names = None
        self.app = None

        self.frame_counter = 0
        self.last_faces = []
        self.last_infer_ms = 0.0
        self.score_buffer = deque(maxlen=BURST_SIZE)
        self.estado_acceso = 'DENEGADO'
        self.frames_since_fps = 0
        self.last_fps_time = time.time()
        self.current_fps = 0.0
        self.infer_counter = 0
        
        # Suscripción a la Autopista B (ROS 2)
        self.image_sub = self.create_subscription(
            Image,
            camera_topic,
            self.image_callback,
            qos_profile_sensor_data  # <--- EL CAMBIO CLAVE
        )
        self.get_logger().info(f'Suscrito a imágenes en: {camera_topic}')

        # Publicadores
        self.result_pub = self.create_publisher(AlarmReport, '/alarms/raw', 10)
        self.debug_pub = self.create_publisher(Image, '/face_recognition/debug_image', 10)

        # Cargar Base de Datos
        self.pkg_share = get_package_share_directory('b_face_recognition')
        self.db_path = os.path.join(self.pkg_share, 'data', ARCHIVO_DB)
        self.get_logger().info(f'Buscando base de datos en: {self.db_path}')

        # 2. Verificar si el archivo existe físicamente antes de cargarlo
        if os.path.exists(self.db_path):
            try:
                # Intentamos la carga mediante tu función cargar_embeddings
                self.known_embeddings, self.known_names = cargar_embeddings(self.db_path)
                
                if self.known_embeddings is not None:
                    self.get_logger().info(f'✅ DB Facial cargada. Rostros conocidos: {self.known_names}')
                else:
                    self.get_logger().error(f"❌ El archivo existe pero cargar_embeddings devolvió None: {self.db_path}")
                    raise RuntimeError("Error estructural en el archivo de base de datos.")
            except Exception as e:
                self.get_logger().error(f'❌ Error crítico al leer el archivo .npz: {str(e)}')
                raise RuntimeError(f"No se pudo procesar la DB Facial: {e}")
        else:
            self.get_logger().error(f'⚠️ ARCHIVO NO ENCONTRADO en la ruta: {self.db_path}')
            raise RuntimeError(f"Falta el archivo indispensable: {ARCHIVO_DB}")
        
        # Iniciar InsightFace
        self.get_logger().info(f'Iniciando InsightFace ({MODELO_INSIGHTFACE})... Esto tomará unos segundos.')
        
        os.makedirs(TRT_CACHE_DIR, exist_ok=True)
        providers = [
            (
                'TensorrtExecutionProvider',
                {
                    'device_id': 0,
                    'trt_engine_cache_enable': True,
                    'trt_engine_cache_path': TRT_CACHE_DIR,
                    'trt_fp16_enable': True,
                }
            ),
            ('CUDAExecutionProvider', {'device_id': 0}),
        ]
        self.app = FaceAnalysis(
            name=MODELO_INSIGHTFACE,
            allowed_modules=['detection', 'recognition'],
            providers=providers
        )
        self.app.prepare(ctx_id=0, det_size=(640, 640))

        for nombre_modelo, instancia_modelo in self.app.models.items():
            session = getattr(instancia_modelo, 'session', None)
            if session:
                proveedores_activos = session.get_providers()
                proveedor_primario = proveedores_activos[0]
                
                if proveedor_primario == 'TensorrtExecutionProvider':
                    self.get_logger().info(
                        f" -> Sub-modelo '{nombre_modelo}': TensorRT ✅ (FP16 activo)"
                    )
                elif proveedor_primario == 'CUDAExecutionProvider':
                    self.get_logger().warn(
                        f" -> Sub-modelo '{nombre_modelo}': CUDA ⚠️ "
                        f"(TRT 10.x no disponible en JetPack 6.0)"
                    )
                else:
                    self.get_logger().fatal(
                        f"¡CRÍTICO! '{nombre_modelo}' corriendo en CPU. Abortando."
                    )
                    raise RuntimeError(
                        f"Autodestrucción: '{nombre_modelo}' en CPU. "
                        f"Verifica que --runtime nvidia esté activo."
                    )

        self.get_logger().info(
            '✅ Certificación de Hardware: InsightFace anclado a GPU (CUDA/TensorRT).'
        )

    def evaluate_faces(self, faces, display_frame):
        faces_to_process = faces[:1]
        selected_name, selected_score, access_status = "NO_FACE", -1.0, "NO_FACE"
        rostro_valido_procesado = False

        for face in faces_to_process:
            box = face.bbox.astype(int)
            x1, y1, x2, y2 = box[0], box[1], box[2], box[3]

            area = area_rostro(face)
            if area < AREA_MINIMA: continue
            
            w, h = x2 - x1, y2 - y1
            if h == 0: continue
            if not (ASPECT_RATIO_MIN <= w / h <= ASPECT_RATIO_MAX): continue

            # Inferencia
            emb_actual = normalizar_vector(face.embedding)
            similitudes = np.dot(self.known_embeddings, emb_actual)
            idx = np.argmax(similitudes)
            score = similitudes[idx]
            self.score_buffer.append(score)
            avg_score = sum(self.score_buffer) / len(self.score_buffer)

            if self.estado_acceso == "DENEGADO" and avg_score >= UMBRAL_ENTRADA:
                self.estado_acceso = "ACCESO"
            elif self.estado_acceso == "ACCESO" and avg_score < UMBRAL_SALIDA:
                self.estado_acceso = "DENEGADO"

            nombre = self.known_names[idx] if self.estado_acceso == "ACCESO" else "Desconocido"
            color_box = (0, 255, 0) if self.estado_acceso == "ACCESO" else (0, 0, 255)

            selected_name, selected_score, access_status = nombre, avg_score, self.estado_acceso
            rostro_valido_procesado = True

            if self.show_debug and display_frame is not None:
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), color_box, 2)
                cv2.rectangle(display_frame, (x1, y1 - 60), (x2, y1), (10, 10, 10), -1)
                cv2.putText(display_frame, nombre, (x1 + 5, y1 - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(display_frame, f"{access_status} ({avg_score:.2f})", (x1 + 5, y1 - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color_box, 1)

        if not rostro_valido_procesado:
            self.score_buffer.clear()
            self.estado_acceso = 'DENEGADO'

        return selected_name, selected_score, access_status

    def image_callback(self, msg):
        try:
            # BYPASS DE CV_BRIDGE (Matemática pura de Numpy)
            frame = (np.frombuffer(msg.data, dtype=np.uint8)
                     .reshape((msg.height, msg.step))[:, :msg.width * 3]
                     .reshape(msg.height, msg.width, 3))
        except Exception as e:
            self.get_logger().error(f"Error procesando imagen: {e}")
            return
        
        self.frame_counter += 1
        self.frames_since_fps += 1
        now = time.time()
        elapse_fps = now - self.last_fps_time

        display_frame = frame.copy() if self.show_debug else None

        if elapse_fps >= 1.0:
            self.current_fps = self.frames_since_fps / elapse_fps
            self.frames_since_fps = 0
            self.last_fps_time = now
    
        should_infer = (self.frame_counter - 1) % INFER_EVERY_N_FRAMES == 0
        if should_infer:
            infer_start = time.time()
            faces = self.app.get(frame)
            infer_ms = (time.time() - infer_start) * 1000
            self.infer_counter += 1
            faces = sorted(faces, key=area_rostro, reverse=True)
            self.last_faces = faces
            self.last_infer_ms = infer_ms
        else:
            faces = self.last_faces
            infer_ms = self.last_infer_ms

        selected_name, selected_score, access_status = self.evaluate_faces(faces, display_frame)
        
        if should_infer and self.infer_counter % LOG_INFERENCE_EVERY == 0:
            self.get_logger().info(f"infer_ms={infer_ms:.1f} | name={selected_name} | status={access_status}")
        
        if selected_name == "Desconocido" and access_status == "DENEGADO":
            alarm_msg = AlarmReport()
            # Coincidencia exacta con la especificación recibida:
            alarm_msg.priority = 1
            alarm_msg.alarm_type = "INTRUSO"
            alarm_msg.source_node = "face_recognition_node" # Aquí puedes dejar el nombre del nodo real
            alarm_msg.is_emergency = True
            
            self.result_pub.publish(alarm_msg)
            self.get_logger().warn(f"ALARMA ENVIADA: {alarm_msg.alarm_type} desde {alarm_msg.source_node}")

        # Publicar Imagen sin CV_BRIDGE
        if self.show_debug and display_frame is not None:
            cv2.putText(display_frame, f"FPS: {self.current_fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            msg_debug = Image()
            msg_debug.header.stamp = self.get_clock().now().to_msg()
            msg_debug.header.frame_id = "camera"
            msg_debug.height = display_frame.shape[0]
            msg_debug.width = display_frame.shape[1]
            msg_debug.encoding = "bgr8"
            msg_debug.is_bigendian = 0
            msg_debug.step = display_frame.shape[1] * 3
            msg_debug.data = display_frame.tobytes()
            
            self.debug_pub.publish(msg_debug)

def main(args=None):
    rclpy.init(args=args)
    node = FaceRecognitionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()