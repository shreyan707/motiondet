import cv2
import serial
import time
import requests
import os
import numpy as np
from datetime import datetime
try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    FACE_REC_AVAILABLE = False
    print("WARNING: face_recognition library not found. Identification will be disabled.")
from flask import Flask, render_template

BOT_TOKEN = "8686246587:AAH0uA17Cv5bOZ3rGu39nDmRyPbipOymqX8"
CHAT_ID = "6406796423"

arduino = serial.Serial('COM8',9600)

app = Flask(__name__)

last_intruder = "No intrusions yet"
current_score = 0
active_factors = []

# --- Threat Scoring Constants ---
NIGHT_START = 22
NIGHT_END = 6
SCORE_THRESHOLD = 60
PROXIMITY_BOUNDARY = 100 # cm

# --- Tracking State ---
last_cx = 0
last_cy = 0
last_move_time = 0

# --- Facial Recognition Setup ---
KNOWN_FACES_DIR = "known_faces"
known_encodings = []
known_names = []

def load_known_faces():
    global known_encodings, known_names
    if not FACE_REC_AVAILABLE:
        return
    
    print("Loading known faces...")
    if not os.path.exists(KNOWN_FACES_DIR):
        os.makedirs(KNOWN_FACES_DIR)
    
    for filename in os.listdir(KNOWN_FACES_DIR):
        if filename.endswith((".jpg", ".png", ".jpeg")):
            path = os.path.join(KNOWN_FACES_DIR, filename)
            try:
                image = face_recognition.load_image_file(path)
                encodings = face_recognition.face_encodings(image)
                
                if len(encodings) > 0:
                    known_encodings.append(encodings[0])
                    # Use filename without extension as name
                    known_names.append(os.path.splitext(filename)[0])
                    print(f"Loaded: {filename}")
            except Exception as e:
                print(f"Error loading {filename}: {e}")

load_known_faces()
# --------------------------------

def send_notification(image):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    files = {"photo": open(image,"rb")}

    data = {
        "chat_id": CHAT_ID,
        "caption": "🚨 UNKNOWN ENTITY DETECTED! 🚨"
    }

    requests.post(url, files=files, data=data)


@app.route("/")
def dashboard():
    global current_score, active_factors
    return render_template("dashboard.html", event=last_intruder, score=current_score, factors=active_factors)


def detection_loop():

    global last_intruder, last_cx, last_cy, last_move_time
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
            
            # --- Parsing V2 Telemetry ---
            if msg.startswith("DETECTION,"):
                try:
                    parts = msg.split(",")
                    arduino_conf = int(parts[1])
                    arduino_dist = int(parts[2])
                except:
                    continue # Malformed data

                blob = cv2.dnn.blobFromImage(
                    cv2.resize(frame,(300,300)),
                    0.007843,
                    (300,300),
                    127.5
                )
                net.setInput(blob)
                detections = net.forward()

                person_detected = False
                p_box = None

                for i in range(detections.shape[2]):
                    confidence = detections[0,0,i,2]
                    if confidence > 0.5:
                        idx = int(detections[0,0,i,1])
                        if classes[idx] == "person":
                            person_detected = True
                            p_box = detections[0,0,i,3:7] * np.array([frame.shape[1], frame.shape[0], frame.shape[1], frame.shape[0]])
                            break

                if person_detected:
                    current_time = time.time()
                    timestamp = time.ctime(current_time)
                    last_detection_time = current_time

                    # 1. Start Scorcing Base (Fusion Confidence)
                    threat_score = 0
                    local_factors = []

                    # 2. Night Time Scoring (+30)
                    h = datetime.now().hour
                    if h >= NIGHT_START or h < NIGHT_END:
                        threat_score += 30
                        local_factors.append("NIGHT_TIME")

                    # 3. Near Boundary (+25)
                    if 0 < arduino_dist < PROXIMITY_BOUNDARY:
                        threat_score += 25
                        local_factors.append("NEAR_BOUNDARY")

                    # 4. Fast Movement (+20)
                    (x1, y1, x2, y2) = p_box.astype("int")
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    if last_cx != 0:
                        pixel_dist = ((cx - last_cx)**2 + (cy - last_cy)**2)**0.5
                        time_delta = current_time - last_move_time
                        if time_delta < 2 and pixel_dist > 80: # If moved > 80 pixels quickly
                            threat_score += 20
                            local_factors.append("FAST_MOVEMENT")
                    
                    last_cx, last_cy = cx, cy
                    last_move_time = current_time

                    # 5. Facial Recognition (+40 if Unknown)
                    is_authorized = False
                    detected_name = "Unknown"
                    if FACE_REC_AVAILABLE:
                        face_locations = face_recognition.face_locations(frame)
                        face_encodings = face_recognition.face_encodings(frame, face_locations)
                        for face_encoding in face_encodings:
                            matches = face_recognition.compare_faces(known_encodings, face_encoding)
                            if True in matches:
                                first_match_index = matches.index(True)
                                detected_name = known_names[first_match_index]
                                is_authorized = True
                                break
                    
                    if not is_authorized:
                        threat_score += 40
                        local_factors.append("UNKNOWN_ENTITY")
                    
                    # Update global dashboard state
                    global current_score, active_factors
                    current_score = min(threat_score, 100) # Cap at 100
                    active_factors = local_factors

                    if is_authorized:
                        last_intruder = f"Authorized User: {detected_name} ({timestamp})"
                    else:
                        last_intruder = f"THREAT LEVEL {current_score}: {detected_name} ({timestamp})"

                    # --- Trigger Notification Logic ---
                    if current_score >= SCORE_THRESHOLD:
                        if current_time - last_notification_time > 10:
                            filename = f"images/intruder_{int(current_time)}.jpg"
                            cv2.imwrite(filename, frame)
                            
                            # Custom Caption for Telegram
                            caption = f"🚨 THREAT DETECTED! 🚨\nScore: {current_score}\nFactors: {', '.join(local_factors)}"
                            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                            files = {"photo": open(filename,"rb")}
                            requests.post(url, files=files, data={"chat_id": CHAT_ID, "caption": caption})
                            
                            last_notification_time = current_time
                    # ------------------------------------


import threading
threading.Thread(target=detection_loop).start()

app.run(port=5000)