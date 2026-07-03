#!/usr/bin/env python3
import os
import multiprocessing as mp
import rclpy
import signal
import queue
from rclpy.utilities import get_rmw_implementation_identifier
from vigilance_interfaces.msg import AlarmReport

def run_domain_99_subscriber(q_alarm, shutdown_event):
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    # Conectado a la IA (Jardín Zen)
    os.environ['ROS_DOMAIN_ID'] = '99'
    os.environ['RMW_IMPLEMENTATION'] = 'rmw_cyclonedds_cpp'
    rclpy.init(signal_handler_options=rclpy.signals.SignalHandlerOptions.NO)
    node = rclpy.create_node('micro_bridge_sub_99')
    
    def alarm_callback(msg):
        q_alarm.put(msg)
        
    node.create_subscription(AlarmReport, '/alarms/raw', alarm_callback, 10)
    
    node.get_logger().info('Puente [RX] escuchando ALARMAS en Dominio 99...')
    node.get_logger().info(f'RMW efectivo: {get_rmw_implementation_identifier()}')
    while rclpy.ok() and not shutdown_event.is_set():
        rclpy.spin_once(node, timeout_sec=0.1)

    node.get_logger().info('Cerrando limpio...')
    try:
        node.destroy_node()
        rclpy.shutdown()
    except Exception:
        pass

def run_domain_0_publisher(q_alarm, shutdown_event):
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    # Conectado al Mundo Exterior (Autopista Principal)
    os.environ['ROS_DOMAIN_ID'] = '0'
    os.environ['RMW_IMPLEMENTATION'] = 'rmw_cyclonedds_cpp'
    rclpy.init(signal_handler_options=rclpy.signals.SignalHandlerOptions.NO)
    node = rclpy.create_node('micro_bridge_pub_0')
    
    pub_alarm = node.create_publisher(AlarmReport, '/alarms/raw', 10)
    
    def timer_callback():
        while True:
            try:
                msg = q_alarm.get_nowait()
            except queue.Empty:
                break
            pub_alarm.publish(msg)
            node.get_logger().info('¡Alarma reenviada al Dominio 0!')
            
            
    node.create_timer(0.1, timer_callback)
    node.get_logger().info('Puente [TX] publicando ALARMAS en Dominio 0...')
    node.get_logger().info(f'RMW efectivo: {get_rmw_implementation_identifier()}')
    while rclpy.ok() and not shutdown_event.is_set():
        rclpy.spin_once(node, timeout_sec=0.1)

    node.get_logger().info('Cerrando limpio...')
    try:
        node.destroy_node()
        rclpy.shutdown()
    except Exception:
        pass

if __name__ == '__main__':
    mp.set_start_method('spawn')
    print("Iniciando Micro-Puente LIGERO (Solo Alarmas) (99 -> 0)...")
    q_alarm = mp.Queue()
    shutdown_event = mp.Event()
    
    p_sub = mp.Process(target=run_domain_99_subscriber, args=(q_alarm, shutdown_event))
    p_pub = mp.Process(target=run_domain_0_publisher, args=(q_alarm, shutdown_event))
    p_sub.start()
    p_pub.start()
    
    try:
        p_sub.join()
        p_pub.join()
    except KeyboardInterrupt:
        shutdown_event.set()
        p_sub.join(timeout=5.0)
        p_pub.join(timeout=5.0)
        if p_sub.is_alive(): p_sub.terminate()
        if p_pub.is_alive(): p_pub.terminate()