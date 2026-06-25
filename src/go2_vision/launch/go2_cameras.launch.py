from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # IP de tu Backend
    backend_ip = '10.20.0.53'

    return LaunchDescription([
        # CÁMARA 1: FRONTAL (Integrada del Perro)
        Node(
            package='go2_vision',
            executable='camera_stream',
            name='front_camera_node',
            namespace='front',
            parameters=[{
                'camera_path': '/dev/v4l/by-path/platform-3610000.usb-usb-0:4.4:1.0-video-index0',
                'udp_port': 5000,
                'backend_ip': backend_ip,
                'frame_id': 'front_camera_link'
            }]
        ),

        # CÁMARA 2: IZQUIERDA (Arducam - Lateral)
        ##Node(
        #    package='go2_vision',
        #    executable='camera_stream',
        #    name='left_camera_node',
        #    namespace='left',
        #    parameters=[{
        #        'camera_path': '/dev/v4l/by-path/platform-3610000.usb-usb-0:4.2:1.0-video-index0',
        #        'udp_port': 5002,
        #        'backend_ip': backend_ip,
        #        'frame_id': 'left_camera_link'
        #    }]
        #),

        # CÁMARA 3: DERECHA (Aducam Lateral)
        Node(
            package='go2_vision',
            executable='camera_stream',
            name='right_camera_node',
            namespace='right',
            parameters=[{
                'camera_path': '/dev/v4l/by-path/platform-3610000.usb-usb-0:4.2:1.0-video-index0',
                'udp_port': 5001,
                'backend_ip': backend_ip,
                'frame_id': 'right_camera_link'
            }]
        ),
    ])
