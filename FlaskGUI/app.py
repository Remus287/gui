from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO
from threading import Lock
import csv
import json
import os
import random

import configuration

async_mode = None

# GLOBAL VARIABLES
actuator_buttons = []
sensors = []


app = Flask(__name__, static_url_path='/static')
socketio = SocketIO(app, async_mode=async_mode)
#TODO: what should thread equal, same with async_mode at top of page
thread = None
thread_lock = Lock()



@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        buttonID = request.form.get('button')

        if buttonID == 'actuators':
            return redirect(url_for('actuators'))
        if buttonID == 'sensors':
            return redirect(url_for('sensors'))

    return render_template('index.html')


# TODO: better way than using global variables, verify config
@app.route('/loadconfig', methods=['GET', 'POST'])
def loadconfig():
    global actuator_buttons, sensors
    if request.method == 'POST':
        buttonID = request.form.get('button')

        if buttonID == 'Button 1':
            config_bytes = request.files['file'].read()
            actuator_buttons, sensors = configuration.load_config(config_bytes)
            print("actuator_buttons: ", actuator_buttons)
            print("sensors: ", sensors)

    return render_template('loadconfig.html')

    
@app.route('/actuators', methods=['GET'])
def actuators():
    return render_template('actuators.html', actuator_buttons=actuator_buttons)  

@app.route('/sensors')
def sensors():
    return render_template('sensors.html', async_mode=socketio.async_mode)

@socketio.on('received_actuator_button_press')
def handle_actuator_button_press(buttonID):
    print('received button press: ', buttonID)



@socketio.on('actuator_button_coordinates')
def actuator_button_coordinates(get_request_or_coordinate_data):

    # if actuators.html is requesting the coordinates stored in the .json
    if get_request_or_coordinate_data == 'getCoordinates':
        #emit coordinates
        with open(os.path.dirname(os.path.abspath(__file__)) + '/static/coordinates.json', 'r') as file:
            coordinates = json.load(file)
            print("actuators.html is asking for coordinates from .json")
        socketio.emit('get_actuator_button_location_config', coordinates)

    else: # actuators.html is sending new button coordinates for saving
        with open(os.path.dirname(os.path.abspath(__file__)) + '/static/coordinates.json', 'w') as file:
            json.dump(get_request_or_coordinate_data, file)
            print("button coordinates saved to .json file")




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
    while True:
        # do 0.001 for about 950hz
        socketio.sleep(0.001)
        sensors_and_data = packet_sensor_data(sensors)
        socketio.emit('sensor_data', sensors_and_data)


def packet_sensor_data(sensors):
    a = []
    for sensor in sensors:
        a.append([sensor, 100+random.random()])
    return a


if __name__ == '__main__':
    socketio.run(app)
