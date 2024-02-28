import socket
import socketserver
import time

import sys, os

# For ping
# if there are yellow error squiggles under some import stuff ignore it
custom_libs_path = os.path.abspath("./libs")
sys.path.insert(0, custom_libs_path)
from pythonping import ping


# For threading
import threading
from threading import Thread

import configuration
import sensor
import actuator

# this causes the file to run twice
#import app

start_time = time.time()
mote_ping = [None, None, None, None]

# value = [sensor["P and ID"], sensor["Interface Type"], sensor["Sensor or Actuator"], sensor["unit"]]
sensor_and_actuator_dictionary = {'1, 99': ['FireX', None, None, None]}
most_recent_data_packet = {}

actuator_states_and_sensor_tare_states = {}

# Sending config and actuator commands
sock = socket.socket(socket.AF_INET,  # Internet
                     socket.SOCK_DGRAM)  # UDP

def get_ip(mote_id=None):
    if mote_id == None:
        return '127.0.0.1'
    return '192.168.1.' + str(100 + (int(mote_id)))

def send_actuator_command(mote_id, pin_num, state, interface_type='Binary GPIO'):
    if interface_type != 'Heartbeat':
        print(f"Sending {state} command to pin {pin_num} on MoTE {mote_id}, via {interface_type}")
    if interface_type == 'servoPWM_12V':
            #the GPIO pin we connect to is equal to the 5V the servo is "connected" to + 28
            #send_actuator_command(mote_id, 22, True)
            pass
    actuator_write_command = 0b10000000
    actuator_state_mask = 0b01000000 if state else 0
    interface_type_number = configuration.get_interface_type_number(
        interface_type) & 0b00111111
    config_byte = actuator_write_command | actuator_state_mask | interface_type_number
    ip = get_ip(mote_id=mote_id)
    #for _ in range(3):
    sock.sendto(bytes([int(pin_num), config_byte]), (ip, 8888))

def send_heartbeat():
    while True:
        # send 3 UDP packets for redundancy
        send_actuator_command(1, 100, True, interface_type='Heartbeat')
        send_actuator_command(2, 100, True, interface_type='Heartbeat')
        send_actuator_command(3, 100, True, interface_type='Heartbeat')
        #print("sending hearbeat")S
        time.sleep(2.5)

heartbeat_thread = Thread(target=send_heartbeat, daemon=True)

def send_config_to_mote(sensor_list, actuator_list):
    global sensor_and_actuator_dictionary
    sensor_and_actuator_dictionary.update(create_sensor_dictionary(sensor_list + actuator_list))
    sensors_and_actuators_list = sensor_list + actuator_list
    print("sent sensor config data to mote")
    for m in range(1, 4):
        reset_command = bytearray(2)
        reset_command[0] = 0
        reset_command[1] |= 0b00000000
        reset_command[1] |= 0b00111111 & configuration.get_interface_type_number('Clear_Config')

        sock.sendto(reset_command, (get_ip(m), 8888))

        try:
            heartbeat_thread.start()
        except:
            print("heartbeat thread already started")

        try:
            ping_thread.start()
        except:
            print("ping thread already started")

    for sensor in sensors_and_actuators_list:
        #skip labjacks
        if int(sensor['Mote id']) >= 10:
            continue

        ip = get_ip(sensor['Mote id'])  # '192.168.2.'+sensor['Mote id']

        # See Readme for explenation of config_command
        config_command = bytearray(2)  # 2 byte byte array
        config_command[0] = int(sensor['Pin'])  # set first byte

        # set this to 0b10000000 for actuator write command
        config_command[1] |= 0b00000000
        config_command[1] |= 0b00111111 & configuration.get_interface_type_number(
            sensor['Interface Type'])

        sock.sendto(config_command, (ip, 8888))
        time.sleep(0.1)

def ping_mote():
    while True:
        for moteID in range(1, 5):
            ip_address = get_ip(mote_id=moteID)
            pingResponse = ping(ip_address, count=1, timeout=0.100) # 100msec ping is too high
            success = pingResponse.stats_packets_returned
            delay = pingResponse.rtt_avg_ms
            if success > 0:
                mote_ping[moteID-1] = delay
                #print("thread ping", delay)
            else:
                mote_ping[moteID-1] = None
                #print("ping for mote " +  str(moteID) +  " returned error code 1")
        time.sleep(1)

ping_thread = Thread(target=ping_mote, daemon=True)   # Make a new thread to run ping_mote function


def generate_handler():
    class TelemetryRecieveHandler(socketserver.BaseRequestHandler):
        def handle(self):
            data = self.request
            mote_id = self.client_address[0][-1]
            data_to_send_to_frontend = convert_to_values(data, mote_id)

            global sensor_and_actuator_dictionary
            global most_recent_data_packet
            global actuator_states_and_sensor_tare_states

            for data in data_to_send_to_frontend:
                pin_num = int(data["Pin"])

                if pin_num == 99: 
                    # fireX pin num
                    pass
                elif pin_num > 99: 
                    # ack for a actuator press
                    p_and_id, interface_type, sensor_or_actuator, unit = sensor_and_actuator_dictionary[str(data["Mote id"]) + ", " + str(int(data["Pin"]) - 100)]
                    state = data["Value"]
                    actuator.log_actuator_ack(p_and_id, state)
                else: 
                    # a sensor reading
                    p_and_id, interface_type, sensor_or_actuator, unit = sensor_and_actuator_dictionary[str(data["Mote id"]) + ", " + str(data["Pin"])]
                    #sensor_value = convert_units(data["Value"], unit)
                    most_recent_data_packet[p_and_id] = data["Value"]
            
            #print(most_recent_data_packet["TNSY"])
            sensor.log_sensor_data(time.time() - start_time, most_recent_data_packet)


    return TelemetryRecieveHandler

def telemetry_reciever():
    try:
        HOST, PORT = "0.0.0.0", 8888
        with socketserver.UDPServer((HOST, PORT), generate_handler()) as server:
            server.serve_forever()
            print("telemetry thread started")
    except:
        print('telermetry thread already started, cannot start another')

def start_telemetry_thread():
    telemetry_thread = Thread(target=telemetry_reciever, daemon=True)
    telemetry_thread.start()


def convert_to_values(packet, mote_id):
    data = packet[0]
    parsed_data = []
    for i in range(len(data)//5):
        pin_num = data[5*i]
        value = int.from_bytes(data[5*i+1:5*i+5], byteorder='little', signed=True) # Tim did not have signed parameter in his networking code
        parsed_data.append({'Mote id': mote_id, 'Pin': pin_num, 'Value': value})
    return parsed_data


# converts list of sensors and actuators to a single dictionary for O(1) lookup time
def create_sensor_dictionary(sensor_and_actuator_list):
    dict = {}
    for sensor in sensor_and_actuator_list:
        dict[sensor["Mote id"] + ", " + sensor["Pin"]] = [sensor["P and ID"], sensor["Interface Type"], sensor["Sensor or Actuator"], sensor["Unit"]]
    return dict

def get_sensor_data():
    global most_recent_data_packet
    return most_recent_data_packet

def updateTares(actuator_states_and_sensor_tare_states_from_app_dot_py):
    global actuator_states_and_sensor_tare_states
    actuator_states_and_sensor_tare_states = actuator_states_and_sensor_tare_states_from_app_dot_py

def convert_units(value, unit):
    pass

def get_mote_ping():
    return mote_ping