#!/usr/bin/env python3
import os
import multiprocessing as mp
import rclpy
from rclpy.node import Node
from vigilance_interfaces.msg import AlarmReport

def run_domain_99_subscriber(q_alarm):
    # Conectado a la IA (Jardín Zen)
    os.environ['ROS_DOMAIN_ID'] = '99'
    rclpy.init()
    node = rclpy.create_node('micro_bridge_sub_99')
    
    def alarm_callback(msg):
        q_alarm.put(msg)
        
    node.create_subscription(AlarmReport, '/alarms/raw', alarm_callback, 10)
    
    node.get_logger().info('Puente [RX] escuchando ALARMAS en Dominio 99...')
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

def run_domain_0_publisher(q_alarm):
    # Conectado al Mundo Exterior (Autopista Principal)
    os.environ['ROS_DOMAIN_ID'] = '0'
    rclpy.init()
    node = rclpy.create_node('micro_bridge_pub_0')
    
    pub_alarm = node.create_publisher(AlarmReport, '/alarms/raw', 10)
    
    def timer_callback():
        while not q_alarm.empty():
            pub_alarm.publish(q_alarm.get())
            node.get_logger().info('¡Alarma reenviada al Dominio 0!')
            
    node.create_timer(0.01, timer_callback)
    node.get_logger().info('Puente [TX] publicando ALARMAS en Dominio 0...')
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    print("Iniciando Micro-Puente LIGERO (Solo Alarmas) (99 -> 0)...")
    q_alarm = mp.Queue()
    
    p_sub = mp.Process(target=run_domain_99_subscriber, args=(q_alarm,))
    p_pub = mp.Process(target=run_domain_0_publisher, args=(q_alarm,))
    
    p_sub.start()
    p_pub.start()
    
    try:
        p_sub.join()
        p_pub.join()
    except KeyboardInterrupt:
        p_sub.terminate()
        p_pub.terminate()