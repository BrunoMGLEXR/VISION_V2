# 🐕 Unitree Go2: Autonomous Edge AI Vision System

![ROS 2](https://img.shields.io/badge/ROS_2-Foxy%20%7C%20Humble-22314E?style=for-the-badge&logo=ros&logoColor=white)
![NVIDIA Jetson](https://img.shields.io/badge/NVIDIA-Jetson_aarch64-76B900?style=for-the-badge&logo=nvidia&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-GStreamer%20%7C%20NVENC-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)

Sistema orquestador de visión autónoma de alto rendimiento para el robot cuadrúpedo **Unitree Go2**. Este proyecto implementa un sistema de reconocimiento facial biométrico (InsightFace `buffalo_l`) ejecutándose estrictamente en el borde (Edge AI), aprovechando la aceleración de hardware de la NVIDIA Jetson interna del robot.

## 🧠 Arquitectura: "Doble Autopista DDS" (Domain Isolation)

El Unitree Go2 nativo inunda la red con tráfico masivo de telemetría y LiDAR vía CycloneDDS, lo que causa errores fatales de memoria (`std::bad_alloc`) al intentar correr nodos pesados de IA en la misma red. Para solucionar esto, hemos implementado una **Arquitectura de Doble Dominio Aislado**:

1. **La Autopista Pública (`ROS_DOMAIN_ID=0`)**: Maneja el tráfico nativo del robot y la comunicación directa con el Backend (Laptop del operador).
2. **El Jardín Zen (`ROS_DOMAIN_ID=99`)**: Un entorno hermético y seguro dentro de un contenedor Docker donde reside la Inteligencia Artificial.

### 📦 Paquetes y Componentes del Workspace

* **`vigilance_interfaces`**: Define el mensaje personalizado `AlarmReport.msg` (Prioridad, tipo de alarma, nodo origen, estado de emergencia).
* **`go2_vision`**: Captura de video eficiente desde cámara UVC. Utiliza OpenCV compilado con **GStreamer** para la compresión por hardware (`NVENC` / `nvv4l2h264enc`), publicando frames redimensionados a 640x640 internamente evitando embotellamientos en la CPU.
* **`b_face_recognition`**: Nodo orquestador de IA. Ejecuta InsightFace vía `CUDAExecutionProvider` (ONNX Runtime). Aplica la "Regla de Oro de Carga en Frío" (el modelo se instancia una sola vez). Realiza un bypass de `cv_bridge` para maximizar el rendimiento.
* **`simple_bridge.py`**: Multiplexor ligero (multiprocessing) en el Host que escucha anomalías en el Dominio 99 y las inyecta en el Dominio 0.
* **`third_party/`**: Dependencias y librerías externas necesarias para el procesamiento.

---

## ⚙️ Requisitos Previos

* **Hardware:** Robot Unitree Go2 (NVIDIA Jetson aarch64 interna).
* **Cámara:** Cámara externa USB UVC (ej. 8MP A219 Autofocus) conectada al robot.
* **SO Base:** Ubuntu (JetPack 5.1.1, CUDA 11.4).
* **Software:** Docker, ROS 2.

---

## 🔨 Instrucciones de Compilación

**⚠️ ADVERTENCIA CRÍTICA:** Todo el código de ROS 2 debe compilarse **DENTRO** del contenedor Docker para garantizar el enlace correcto con las librerías de NVIDIA y OpenCV-GStreamer.

1. Accede al robot vía SSH (preferiblemente por Ethernet IP `192.168.123.18` para evitar cortes).
2. Inicia tu contenedor Docker interactivo (con soporte para GPU).
3. Navega a la raíz del workspace:
   ```bash
   cd /ruta/hacia/bruno_ws
4. Compila utilizando colcon:
colcon build --symlink-install
5. Fuentea el entorno:
source install/setup.bash

## 🚀 Comandos de Ejecución
El sistema se orquesta en tres terminales distintas:
1. El Puente de Comunicaciones (Host Jetson - Fuera de Docker)
Habilita el reenvío de mensajes de emergencia hacia el operador:
# Asegúrate de estar en ROS_DOMAIN_ID=0
python3 simple_bridge.py
2. Lanzar los Ojos del Robot (Dentro de Docker)
Inicia la captura por GStreamer y publica en el entorno aislado:
export ROS_DOMAIN_ID=99
ros2 launch go2_vision go2_cameras.launch.py
3. Iniciar la Inteligencia Artificial (Dentro de Docker)
Levanta el orquestador biométrico:
export ROS_DOMAIN_ID=99
ros2 run b_face_recognition face_node


### Nota sobre Modelos Pesados: Los modelos de InsightFace (.npz, .onnx, etc.) no están incluidos en este repositorio para mantener limpio el historial. Deben descargarse manualmente y ubicarse en el directorio correspondiente antes de la ejecución.