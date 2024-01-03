from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_socketio import SocketIO
from threading import Lock
import csv
import json
import os
import random
import time

import configuration

async_mode = None

# GLOBAL VARIABLES
actuator_buttons = []
sensor_list = []
armed = False

# REMOVE BEFORE DEPLOYMENT
actuator_buttons = [{'Mote id': '1', 'Sensor or Actuator': 'actuator', 'Interface Type': 'servoPWM', 'Human Name': 'Nitrogen engine purge', 'Pin': '0', 'P and ID': 'VPTE'}, {'Mote id': '1', 'Sensor or Actuator': 'actuator', 'Interface Type': 'Binary GPIO', 'Human Name': 'Fuel bang-bang', 'Pin': '0', 'P and ID': 'VNTB'}, {'Mote id': '1', 'Sensor or Actuator': 'actuator', 'Interface Type': 'servoPWM', 'Human Name': 'Fuel tank vent', 'Pin': '1', 'P and ID': 'VFTV'}, {'Mote id': '1', 'Sensor or Actuator': 'actuator', 'Interface Type': 'Binary GPIO', 'Human Name': 'Ox bang-bang', 'Pin': '0', 'P and ID': 'VNTO'}, {'Mote id': '1', 'Sensor or Actuator': 'actuator', 'Interface Type': 'servoPWM', 'Human Name': 'Ox tank fill', 'Pin': '0', 'P and ID': 'VOTF'}]
sensor_list = [{'Mote id': '2', 'Sensor or Actuator': 'sensor', 'Interface Type': 'i2c ADC 1ch', 'Human Name': 'Nitrogen storage bottle pressure', 'Pin': '0', 'P and ID': 'PNTB', 'unit': 'C'}, {'Mote id': '2', 'Sensor or Actuator': 'sensor', 'Interface Type': 'i2c ADC 1ch', 'Human Name': 'Ox storage bottle pressure', 'Pin': '1', 'P and ID': 'POTB', 'unit': 'bar'}, {'Mote id': '2', 'Sensor or Actuator': 'sensor', 'Interface Type': 'i2c ADC 1ch', 'Human Name': 'Nitrogen storage bottle pressure', 'Pin': '2', 'P and ID': 'PNTB2', 'unit': 'C'}, {'Mote id': '2', 'Sensor or Actuator': 'sensor', 'Interface Type': 'i2c ADC 1ch', 'Human Name': 'Ox storage bottle pressure', 'Pin': '3', 'P and ID': 'POTB2', 'unit': 'bar'}]


app = Flask(__name__, static_url_path='/static')
socketio = SocketIO(app, async_mode=async_mode)
#TODO: what should thread equal, same with async_mode at top of page
thread = None
thread_lock = Lock()



@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        buttonID = request.form.get('button')

        if buttonID == 'armDisarm':
            global armed
            if not armed:
                armed = True
                print("Stand is ARMED")
            else:
                armed = False
                print("Stand is DISARMED")

        if buttonID == 'actuators':
            return redirect(url_for('actuators'))
        if buttonID == 'sensors':
            return redirect(url_for('sensors'))
        if buttonID == 'pidview':
            return redirect(url_for('pidview'))

    return render_template('index.html', armed=armed)

# TODO: better way than using global variables, verify config
@app.route('/loadconfig', methods=['GET', 'POST'])
def loadconfig():
    global actuator_buttons, sensor_list
    if request.method == 'POST':
        buttonID = request.form.get('button')

        if buttonID == 'Button 1':
            config_bytes = request.files['file'].read()
            actuator_buttons, sensor_list = configuration.load_config(config_bytes)
            #print("actuator_buttons: ", actuator_buttons)
            #print("sensors: ", sensor_list)

    return render_template('loadconfig.html')

    
@app.route('/pidview', methods=['GET'])
def pidview():
    if armed:
        #REMOVE BEFORE DEPLOYMENT
        config_uploaded()
        return render_template('pidview.html', actuator_buttons=actuator_buttons, sensor_list=sensor_list)
    return redirect(url_for('index'))

@app.route('/sensors')
def sensors():
    #REMOVE BEFORE DEPLOYMENT
    config_uploaded()
    return render_template('sensors.html')

@app.route('/actuators', methods=['GET'])
def actuators():
    if armed:
        #REMOVE BEFORE DEPLOYMENT
        config_uploaded()
        return render_template('actuators.html', actuator_buttons=actuator_buttons)
    return redirect(url_for('index'))




@socketio.on('received_actuator_button_press')
def handle_actuator_button_press(buttonID, state):
    print('received actuator button press: ', buttonID, state)

@socketio.on('tare_untare_button_press')
def tare_untare_button_press(buttonID, state):
    print('received tare/untare event: ', buttonID, state)

@socketio.on('actuator_button_coordinates')
def actuator_button_coordinates(get_request_or_coordinate_data):

    # if pidview.html is requesting the coordinates stored in the .json
    if get_request_or_coordinate_data == 'getCoordinates':
        #emit coordinates
        with open(os.path.dirname(os.path.abspath(__file__)) + '/static/coordinates.json', 'r') as file:
            coordinates = json.load(file)
            print("pidview.html is requesting coordinates from .json")
        socketio.emit('get_actuator_button_location_config', coordinates)

    else: # pidview.html is sending new button coordinates for saving
        with open(os.path.dirname(os.path.abspath(__file__)) + '/static/coordinates.json', 'w') as file:
            json.dump(get_request_or_coordinate_data, file)
            print("button coordinates saved to .json file")






# FUNCTIONS BELOW RELATE TO GETTING SENSOR DATA IN BACKGROUND THREAD
@socketio.on('config_uploaded')
def config_uploaded():
    global thread
    with thread_lock:
        if thread is None:   
            thread = socketio.start_background_task(background_thread)
def background_thread():
    """Example of how to send server generated events to clients."""
    # if this delay is not here code fails
    socketio.sleep(1)
    start_time = time.time()
    current_time = start_time
    while True:
        
        sensors_and_data = packet_sensor_data(sensor_list)

        # testing shows we get data at 3khz with random, 6khz with a predetermined constant; ex: 1
        # with open("sensor_data_log", mode='a', newline='') as csv_file:
        #     csv_writer = csv.writer(csv_file)
        #     csv_writer.writerow([current_time] + sensors_and_data)

        current_time = time.time()
        if (current_time - start_time) >= (1/30):
            socketio.emit('sensor_data', sensors_and_data)
            start_time = current_time


# Dummy data function, this function should FETCH data from udp packet
def packet_sensor_data(sensor_list):
    a = []
    for sensor in sensor_list:
        a.append([sensor, round(9999+random.random(), 5)])
    return a


if __name__ == '__main__':
    socketio.run(app)
