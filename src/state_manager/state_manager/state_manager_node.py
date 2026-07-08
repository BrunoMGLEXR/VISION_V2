#!/usr/bin/env python3
"""State Manager: coordinador central de estado del sistema de vigilancia.

Este nodo es el cerebro de coordinación del robot cuadrúpedo centinela. NO hace
visión por computadora: únicamente mantiene el estado de cada persona detectada
(track), decide cuándo pedir autenticación biométrica, aplica un doble mecanismo
de olvido y levanta alarmas.

Portabilidad: ROS2 puro (rclpy). Sin dependencias de GPU/CUDA/cv2/insightface/
numpy, por lo que corre de forma idéntica en una laptop x86 sin GPU (hoy) y en
una NVIDIA Jetson (al portarlo después).

NOTA: Esto es un ANDAMIAJE. Los mecanismos están intencionalmente sin
implementar (ver los TODOs numerados); se completarán paso a paso.
"""

from dataclasses import dataclass #, field: reservado para pasos futuros (default_factory)
from typing import Dict, Optional

import rclpy
from rclpy.node import Node

from vigilance_interfaces.msg import TrackArray
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy

@dataclass
class TrackState:
    """Estado por-track que mantiene el State Manager."""

    track_uuid: str
    name: Optional[str] = None
    auth_status: str = "Pending"          # "Pending" / "Authorized" / "Intruso"
    first_seen: float = 0.0               # timestamp de aparición (timer de alarma)
    last_seen: float = 0.0                # timestamp de última detección (olvido geométrico)
    last_bbox: Optional[tuple] = None
    auth_requested: bool = False          # evita re-pedir autenticación repetidamente
    visibility: str = "Visible"           # "Visible" / "RecentlyLost" / "Forgotten"
    # RESERVADO para Re-ID futuro (no usar en MVP)
    appearance_embedding: Optional[object] = None


class StateManagerNode(Node):
    """Nodo coordinador central del estado de vigilancia."""

    def __init__(self):
        super().__init__('state_manager_node')

        # --- Parámetros ROS2 -------------------------------------------------
        # Segundos antes de alarmar por no-identificación.
        self.declare_parameter('alarm_timeout_sec', 30.0)
        # Segundos sin bbox antes de olvidar un track (olvido geométrico).
        self.declare_parameter('geometric_forget_sec', 3.0)
        # TTL de la caché de identidad.
        self.declare_parameter('identity_cache_ttl_sec', 300.0)

        # --- Estado interno --------------------------------------------------
        # Diccionario de tracks activos, indexados por su UUID.
        self.tracks: Dict[str, TrackState] = {}

        self.get_logger().info('state_manager_node iniciado correctamente.')

        # --- Paso 2: suscripción a tracks de entrada ---
        tracks_qos = QoSProfile(
            reliability = QoSReliabilityPolicy.BEST_EFFORT,
            history = QoSHistoryPolicy.KEEP_LAST,
            depth = 2,
        )
        self.tracks_sub = self.create_subscription(
            TrackArray,
            '/perception/tracks',
            self._on_tracks_received,
            tracks_qos,
        )
        self.get_logger().info('Suscrito a /perception/tracks')
        # --- Paso 3: timer de purga (olvido geométrico + TTL) ---
        self.forget_timer = self.create_timer(1.0, self._check_forgetting)
        # TODO Paso 4: blackboard - publisher a /biometrics/auth_request y
        #              subscriber a /biometrics/auth_status
        # TODO Paso 5: máquina de estados de alarma + timer de N segundos
        # TODO Paso 6: publisher de AlarmReport a /alarms/raw

    # --- Callbacks y mecanismos (placeholders) -------------------------------

    def _on_tracks_received(self, msg):
        now = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        for person in msg.tracks:
            uuid = person.track_uuid
            bbox = (person.x_min, person.y_min, person.width, person.height)
            if uuid not in self.tracks:
                # Track NUEVO: crear el estado Pending
                self.tracks[uuid] = TrackState(
                    track_uuid = uuid,
                    first_seen = now,
                    last_seen = now,
                    last_bbox = bbox,
                )
            else: 
                # Track CONOCIDO: solo actualizar presencia, conservar el resto
                track = self.tracks[uuid]
                track.last_seen = now
                track.last_bbox = bbox
                if track.visibility == "RecentlyLost":
                    track.visibility = "Visible"
                    self.get_logger().info(
                        f'Track {track.track_uuid} -> Visible (reaparece)'
                    ) 
            self.get_logger().info(
                f'Tracks activos: {len(self.tracks)} | UUIDs: {list(self.tracks.keys())}'
            ) 

    def _check_forgetting(self):
        now = self.get_clock().now().nanoseconds * 1e-9
        geometric_forget = self.get_parameter('geometric_forget_sec').value
        identity_ttl = self.get_parameter('identity_cache_ttl_sec').value

        to_forget = [] # UUIDs a purgar (recolectar, no borrrar durante iteración)

        for track in self.tracks.values():
            elapsed = now - track.last_seen
            # Transición 1: Visible -> RecentlyLost (olvido geométrico)
            if elapsed >= geometric_forget and track.visibility == "Visible":
                track.visibility = "RecentlyLost"
                self.get_logger().info(
                    f'Track {track.track_uuid} -> RecentlyLost '
                    f'(sin verse {elapsed:.1f}s)'
                )
            # Transición 2: RecentlyLost -> Forgotten (TTL de identidad expirado)
            if elapsed >= identity_ttl and track.visibility == "RecentlyLost":
                track.visibility = "Forgotten"
                to_forget.append(track.track_uuid)
                self.get_logger().info(
                    f'Track {track.track_uuid} -> Forgotten '
                    f'(sin verse {elapsed:.1f}s, TTL expirado) - purgado'
                )
        
        # Purga fuera del bucle (evita modificar dict durante iteración)
        for uuid in to_forget:
            del self.tracks[uuid] 

    def _request_auth(self, track):
        # TODO Paso 4: publicar solicitud de autenticación biométrica
        pass

    def _on_auth_status(self, msg):
        # TODO Paso 4: actualizar auth_status del track según la respuesta
        pass

    def _evaluate_alarms(self):
        # TODO Paso 5: máquina de estados de alarma
        pass

    def _publish_alarm(self, track):
        # TODO Paso 6: publicar AlarmReport en /alarms/raw
        pass


def main(args=None):
    rclpy.init(args=args)
    node = StateManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
