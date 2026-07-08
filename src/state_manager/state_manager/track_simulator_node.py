#!/usr/bin/env python3
"""Track Simulator: nodo de PRUEBA que simula un tracker de personas.

Herramienta de testing (NO de producción) para ejercitar el State Manager de
forma aislada en una laptop x86 sin GPU. Publica mensajes TrackArray en
'/perception/tracks' siguiendo un guion temporal, de modo que se pueda observar
el mecanismo de olvido del State Manager sin necesidad del pipeline de visión.

Portabilidad: ROS2 puro (rclpy). Sin cv2/numpy/insightface, corre idéntico en
x86 (hoy) y en NVIDIA Jetson (al portarlo).

Guion temporal (segundos desde el arranque del nodo):
  - [0, 15)  : publica UNA persona 'sim-AAA' con un bbox de ejemplo.
  - [15, 25) : 'sim-AAA' desaparece -> publica TrackArray con lista VACÍA.
  - [25, inf): 'sim-AAA' reaparece con el mismo bbox (simula reentrada).
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy

from vigilance_interfaces.msg import TrackArray, TrackedPerson

# --- Guion temporal (umbrales en segundos, fáciles de ajustar) ---------------
DISAPPEAR_AT_SEC = 15.0   # a partir de aquí 'sim-AAA' desaparece
REAPPEAR_AT_SEC = 25.0    # a partir de aquí 'sim-AAA' reaparece

# --- Parámetros de publicación -----------------------------------------------
PUBLISH_PERIOD_SEC = 0.5  # cada cuánto publica el timer
FRAME_ID = 'sim_camera'

# --- Persona simulada 'sim-AAA' ----------------------------------------------
SIM_TRACK_UUID = 'sim-AAA'
SIM_X_MIN = 10.0
SIM_Y_MIN = 20.0
SIM_WIDTH = 50.0
SIM_HEIGHT = 80.0
SIM_CONFIDENCE = 0.9

# --- Fases del guion (para loguear solo en los cambios) ----------------------
PHASE_PRESENT = 'present'    # sim-AAA visible (aparición inicial)
PHASE_ABSENT = 'absent'      # sim-AAA fuera del campo
PHASE_REAPPEAR = 'reappear'  # sim-AAA reingresa


class TrackSimulatorNode(Node):
    """Publica un guion de TrackArray para probar el State Manager."""

    def __init__(self):
        super().__init__('track_simulator_node')

        # QoS que DEBE coincidir con el suscriptor del State Manager, o no se
        # conectan: BEST_EFFORT, KEEP_LAST, depth=2.
        tracks_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=2,
        )
        self.tracks_pub = self.create_publisher(
            TrackArray,
            '/perception/tracks',
            tracks_qos,
        )

        # Marca de tiempo de arranque, para medir el tiempo transcurrido.
        self._start_time = self.get_clock().now()
        # Fase actual del guion; None fuerza el primer log de fase.
        self._phase = None

        self.timer = self.create_timer(PUBLISH_PERIOD_SEC, self._on_timer)
        self.get_logger().info(
            'track_simulator_node iniciado. Publicando en /perception/tracks '
            f'cada {PUBLISH_PERIOD_SEC}s (guion: aparece->desaparece@'
            f'{DISAPPEAR_AT_SEC}s->reaparece@{REAPPEAR_AT_SEC}s).'
        )

    def _elapsed_sec(self):
        """Segundos transcurridos desde el arranque del nodo."""
        return (self.get_clock().now() - self._start_time).nanoseconds * 1e-9

    def _current_phase(self, elapsed):
        """Determina la fase del guion según el tiempo transcurrido."""
        if elapsed < DISAPPEAR_AT_SEC:
            return PHASE_PRESENT
        if elapsed < REAPPEAR_AT_SEC:
            return PHASE_ABSENT
        return PHASE_REAPPEAR

    def _log_phase_change(self, phase):
        """Loguea SOLO cuando cambia la fase (evita saturar la consola)."""
        if phase == self._phase:
            return
        if phase == PHASE_PRESENT:
            self.get_logger().info('Fase: publicando sim-AAA')
        elif phase == PHASE_ABSENT:
            self.get_logger().info('Fase: sim-AAA desaparecida')
        elif phase == PHASE_REAPPEAR:
            self.get_logger().info('Fase: sim-AAA reaparece')
        self._phase = phase

    def _make_sim_person(self):
        """Construye el TrackedPerson de la persona simulada 'sim-AAA'."""
        person = TrackedPerson()
        person.track_uuid = SIM_TRACK_UUID
        person.x_min = SIM_X_MIN
        person.y_min = SIM_Y_MIN
        person.width = SIM_WIDTH
        person.height = SIM_HEIGHT
        person.confidence = SIM_CONFIDENCE
        return person

    def _on_timer(self):
        elapsed = self._elapsed_sec()
        phase = self._current_phase(elapsed)
        self._log_phase_change(phase)

        msg = TrackArray()
        # Stamp = tiempo REAL actual (crítico: el State Manager mide el paso del
        # tiempo con este valor). NO usar un valor fijo.
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = FRAME_ID

        # En 'absent' la lista queda vacía; en 'present'/'reappear' va sim-AAA.
        if phase in (PHASE_PRESENT, PHASE_REAPPEAR):
            msg.tracks = [self._make_sim_person()]
        else:
            msg.tracks = []

        self.tracks_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = TrackSimulatorNode()
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
