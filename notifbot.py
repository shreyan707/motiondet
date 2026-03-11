import cv2
import serial
import time
import requests
from flask import Flask, render_template

BOT_TOKEN = "8686246587:AAH0uA17Cv5bOZ3rGu39nDmRyPbipOymqX8"
CHAT_ID = "6406796423"

arduino = serial.Serial('COM8',9600)

app = Flask(__name__)

last_intruder = "No intrusions yet"

def send_notification(image):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    files = {"photo": open(image,"rb")}

    data = {
        "chat_id": CHAT_ID,
        "caption": "🚨 Intruder Detected!"
    }

    requests.post(url, files=files, data=data)


@app.route("/")
def dashboard():

    return render_template("dashboard.html", event=last_intruder)


def detection_loop():

    global last_intruder

    net = cv2.dnn.readNetFromCaffe(
        "MobileNetSSD_deploy.prototxt",
        "MobileNetSSD_deploy.caffemodel"
    )

    classes = ["background","aeroplane","bicycle","bird","boat","bottle",
           "bus","car","cat","chair","cow","diningtable","dog","horse",
           "motorbike","person","pottedplant","sheep","sofa","train","tvmonitor"]

    cap = cv2.VideoCapture(0)

    last_detection_time = 0
    last_notification_time = 0

    while True:

        ret, frame = cap.read()

        if time.time() - last_detection_time > 5:
            last_intruder = "No intrusions yet"

        if arduino.in_waiting:

            msg = arduino.readline().decode().strip()

            if msg == "MOTION_DETECTED":

                blob = cv2.dnn.blobFromImage(
                    cv2.resize(frame,(300,300)),
                    0.007843,
                    (300,300),
                    127.5
                )

                net.setInput(blob)

                detections = net.forward()

                person_detected = False

                for i in range(detections.shape[2]):

                    confidence = detections[0,0,i,2]

                    if confidence > 0.5:

                        idx = int(detections[0,0,i,1])

                        if classes[idx] == "person":
                            person_detected = True

                if person_detected:
                    
                    current_time = time.time()
                    last_intruder = time.ctime(current_time)
                    last_detection_time = current_time

                    if current_time - last_notification_time > 10:
                        filename = f"images/intruder_{int(current_time)}.jpg"

                        cv2.imwrite(filename,frame)

                        send_notification(filename)

                        print("INTRUDER DETECTED")
                        last_notification_time = current_time


import threading
threading.Thread(target=detection_loop).start()

app.run(port=5000)