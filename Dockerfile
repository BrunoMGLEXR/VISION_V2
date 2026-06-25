FROM dustynv/ros:humble-ros-base-l4t-r36.3.0

# 1. Instalar dependencias base del sistema y ROS 2
# La imagen dustynv ya trae OpenCV optimizado para Jetson; instalar OpenCV
# desde apt arrastra OpenCV 4.5.4 de Ubuntu y choca con opencv-dev 4.8.1-dirty.
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && apt-get update && apt-get install -y \
    python3-pip \
    libgomp1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ros-humble-sensor-msgs \
    ros-humble-rosidl-default-generators \
    python3-colcon-common-extensions \
    ros-humble-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_INDEX_URL=https://pypi.org/simple

# 2. Actualizar pip
RUN python3 -m pip install --upgrade pip

# 3. Instalar las dependencias exactas de InsightFace
RUN python3 -m pip install \
    "numpy<1.24" \
    "protobuf==3.20.3" \
    scipy tqdm requests matplotlib Pillow scikit-learn \
    "scikit-image==0.24.0" \
    "onnx==1.17.0" \
    coloredlogs flatbuffers sympy packaging "pydantic<2.0"

# 4. Instalamos el ONNX Runtime EXACTO del Jetson Zoo
COPY src/third_party/onnxruntime_gpu-1.18.0-cp310-cp310-linux_aarch64.whl /tmp/
RUN python3 -m pip install --no-deps /tmp/onnxruntime_gpu-1.18.0-cp310-cp310-linux_aarch64.whl \
    && rm /tmp/onnxruntime_gpu-1.18.0-cp310-cp310-linux_aarch64.whl

# 5. Instalamos InsightFace y Albumentations
RUN python3 -m pip install --no-deps "qudida==0.0.4" "albumentations==1.3.1" insightface

# 6. Middleware de ROS 2 (¡SIN EL LD_PRELOAD!)
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all

# 7. Configurar bashrc
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

# 8. Espacio de trabajo y Compilación
WORKDIR /home/bruno_ws
COPY src/src/vigilance_interfaces /home/bruno_ws/src/vigilance_interfaces
COPY src/src/b_face_recognition /home/bruno_ws/src/b_face_recognition
RUN bash -lc "source /opt/ros/humble/setup.bash \
    && colcon build --packages-up-to b_face_recognition --cmake-args -DBUILD_TESTING=OFF"
RUN echo "source /home/bruno_ws/install/setup.bash" >> ~/.bashrc
