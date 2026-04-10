import cv2
import serial
import time
import requests
import os
import numpy as np
from datetime import datetime
from collections import deque
from threading import Thread, Lock
import threading


try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    FACE_REC_AVAILABLE = False
    print("ace_recognition library not found. Identification will be disabled.")

from flask import Flask, render_template, jsonify

# ============================================================================
# CONFIGURATION
# ============================================================================

# Telegram Bot Settings
BOT_TOKEN = "8686246587:AAH0uA17Cv5bOZ3rGu39nDmRyPbipOymqX8"
CHAT_ID = "6406796423"

# Arduino Serial Connection
ARDUINO_PORT = 'COM8'
ARDUINO_BAUD = 9600

# Threat Scoring Constants
NIGHT_START = 22  # 10:00 PM
NIGHT_END = 6     # 6:00 AM
SCORE_THRESHOLD_DAY = 60
SCORE_THRESHOLD_NIGHT = 50  # More sensitive at night
PROXIMITY_BOUNDARY = 100  # cm

# Movement Detection Thresholds
FAST_MOVEMENT_THRESHOLD_XY = 80    # pixels
FAST_MOVEMENT_THRESHOLD_AREA = 40  # percent growth
MOVEMENT_TIME_WINDOW = 8.0         # seconds — must be > Arduino cooldown (5s)

# Notification Settings
NOTIFICATION_COOLDOWN = 10  # seconds between Telegram alerts

# Face Recognition Settings
KNOWN_FACES_DIR = "known_faces"
FACE_RECOGNITION_TOLERANCE = 0.5  # Lower = stricter (default 0.6)

# Image Storage
IMAGE_DIR = "images"
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

# ============================================================================
# GLOBAL STATE VARIABLES
# ============================================================================

# Arduino Connection
arduino = None

# Flask App
app = Flask(__name__)

# Dashboard State
last_intruder = "No intrusions yet"
current_score = 0
active_factors = []
system_status = "INITIALIZING"
total_detections = 0
total_alerts = 0

# Tracking State for Movement Analysis
last_cx = 0
last_cy = 0
last_box_area = 0
last_move_time = 0

# Frame Capture Queue (Non-Blocking)
frame_queue = deque(maxlen=10)
frame_lock = Lock()
capture_active = True
current_frame = None

# Facial Recognition Database
known_encodings = []
known_names = []

# Timing
last_detection_time = 0
last_notification_time = 0

# ============================================================================
# FACIAL RECOGNITION SETUP
# ============================================================================

def load_known_faces():
    """Load all known faces from the known_faces directory"""
    global known_encodings, known_names
    
    if not FACE_REC_AVAILABLE:
        print("⚠️  Face recognition disabled")
        return
    
    print("📂 Loading known faces from", KNOWN_FACES_DIR)
    
    if not os.path.exists(KNOWN_FACES_DIR):
        os.makedirs(KNOWN_FACES_DIR)
        print(f"✅ Created {KNOWN_FACES_DIR} directory. Add authorized user photos here.")
        return
    
    face_count = 0
    for filename in os.listdir(KNOWN_FACES_DIR):
        if filename.lower().endswith((".jpg", ".png", ".jpeg")):
            path = os.path.join(KNOWN_FACES_DIR, filename)
            try:
                image = face_recognition.load_image_file(path)
                encodings = face_recognition.face_encodings(image)
                
                if len(encodings) > 0:
                    known_encodings.append(encodings[0])
                    # Use filename without extension as name
                    name = os.path.splitext(filename)[0]
                    known_names.append(name)
                    face_count += 1
                    print(f"  ✅ Loaded: {name}")
                else:
                    print(f"  ⚠️  No face detected in: {filename}")
            except Exception as e:
                print(f"  ❌ Error loading {filename}: {e}")
    
    print(f"✅ Loaded {face_count} authorized face(s)\n")

# ============================================================================
# IMAGE ENHANCEMENT FOR LOW-LIGHT CONDITIONS
# ============================================================================

def enhance_for_recognition(frame):
    """
    Improve facial recognition accuracy in low-light conditions
    using CLAHE (Contrast Limited Adaptive Histogram Equalization)
    """
    # Convert to LAB color space
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Apply CLAHE to L channel
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    
    # Merge channels and convert back to BGR
    enhanced = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    
    return enhanced

# ============================================================================
# TELEGRAM NOTIFICATION SYSTEM
# ============================================================================

def send_telegram_alert(image_path, caption):
    """Send photo alert to Telegram with threat details"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        
        with open(image_path, "rb") as photo:
            files = {"photo": photo}
            data = {
                "chat_id": CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, files=files, data=data, timeout=10)
            
            if response.status_code == 200:
                print("✅ Telegram alert sent successfully")
                return True
            else:
                print(f"⚠️  Telegram API error: {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Failed to send Telegram alert: {e}")
        return False

def generate_threat_report(score, factors, distance, name, arduino_conf):
    """Generate detailed threat report for Telegram"""
    
    # Threat level emoji
    if score >= 80:
        level_emoji = "🔴"
        level_text = "CRITICAL"
    elif score >= 60:
        level_emoji = "🟠"
        level_text = "HIGH"
    elif score >= 40:
        level_emoji = "🟡"
        level_text = "MEDIUM"
    else:
        level_emoji = "🟢"
        level_text = "LOW"
    
    report = f"{level_emoji} <b>VIGIL THREAT ALERT</b> {level_emoji}\n"
    report += f"━━━━━━━━━━━━━━━━━━━━\n"
    report += f"🎯 <b>Threat Score:</b> {score}/100\n"
    report += f"⚠️ <b>Level:</b> {level_text}\n"
    report += f"👤 <b>Identity:</b> {name}\n"
    report += f"📏 <b>Distance:</b> {distance}cm\n"
    report += f"📊 <b>Sensor Confidence:</b> {arduino_conf}%\n"
    report += f"🕐 <b>Time:</b> {datetime.now().strftime('%I:%M:%S %p')}\n"
    report += f"\n<b>📋 Active Factors:</b>\n"
    
    factor_descriptions = {
        "NIGHT_TIME": "🌙 Night Time (+30)",
        "NEAR_BOUNDARY": "⚠️ Near Boundary (+25)",
        "FAST_MOVEMENT_LATERAL": "⚡ Fast Lateral Movement (+20)",
        "FAST_MOVEMENT_APPROACH": "🏃 Rapid Approach (+20)",
        "UNKNOWN_ENTITY": "❓ Unknown Person (+40)",
        "AUTHORIZED_USER": "✅ Authorized User (-60)"
    }
    
    for factor in factors:
        description = factor_descriptions.get(factor, f"• {factor.replace('_', ' ')}")
        report += f"{description}\n"
    
    return report

# ============================================================================
# DYNAMIC THRESHOLD ADJUSTMENT
# ============================================================================

def get_dynamic_threshold():
    """Adjust threat threshold based on time of day"""
    hour = datetime.now().hour
    
    if hour >= NIGHT_START or hour < NIGHT_END:
        return SCORE_THRESHOLD_NIGHT  # More sensitive at night
    elif 6 <= hour < 9 or 17 <= hour < 22:
        return 65  # Rush hours - slightly higher tolerance
    else:
        return SCORE_THRESHOLD_DAY  # Standard daytime threshold

# ============================================================================
# FRAME CAPTURE THREAD (Non-Blocking)
# ============================================================================

def frame_capture_thread(camera):
    """
    Dedicated thread for continuous frame acquisition
    Prevents frame drops during CPU-intensive AI processing
    """
    global capture_active, current_frame
    
    print("🎥 Frame capture thread started")
    
    while capture_active:
        ret, frame = camera.read()
        if ret:
            with frame_lock:
                frame_queue.append(frame.copy())
                current_frame = frame.copy()
        else:
            print("⚠️  Camera read failed")
            time.sleep(0.1)
        
        time.sleep(0.03)  # ~30 FPS capture rate
    
    print("🎥 Frame capture thread stopped")

# ============================================================================
# ARDUINO SERIAL HANDLER
# ============================================================================

def connect_arduino():
    """Establish serial connection to Arduino"""
    global arduino, system_status
    
    try:
        print(f"🔌 Connecting to Arduino on {ARDUINO_PORT}...")
        arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
        time.sleep(2)  # Wait for Arduino reset
        
        # Wait for ONLINE signal
        start_time = time.time()
        while time.time() - start_time < 5:
            if arduino.in_waiting:
                msg = arduino.readline().decode().strip()
                print(f"📡 Arduino: {msg}")
                if "SYSTEM,ONLINE" in msg:
                    system_status = "ONLINE"
                    print("✅ Arduino connected and ready\n")
                    return True
        
        system_status = "CONNECTED"
        print("⚠️  Arduino connected but no ONLINE signal received\n")
        return True
        
    except serial.SerialException as e:
        print(f"❌ Failed to connect to Arduino: {e}")
        system_status = "DISCONNECTED"
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        system_status = "ERROR"
        return False

def validate_checksum(confidence, distance, timestamp, checksum):
    """Validate Arduino data packet checksum"""
    expected = (confidence + distance + (timestamp % 1000)) % 256
    return checksum == expected

# ============================================================================
# MAIN DETECTION LOOP
# ============================================================================

def detection_loop():
    """
    Main threat detection and scoring engine
    Processes Arduino triggers and performs AI-based threat analysis
    """
    global last_intruder, last_cx, last_cy, last_box_area, last_move_time
    global last_detection_time, last_notification_time
    global current_score, active_factors, system_status
    global total_detections, total_alerts, current_frame
    
    print("🚀 Starting VIGIL Detection Loop\n")
    
    # Load AI Models
    print("🧠 Loading MobileNet SSD model...")
    try:
        net = cv2.dnn.readNetFromCaffe(
            "MobileNetSSD_deploy.prototxt",
            "MobileNetSSD_deploy.caffemodel"
        )
        print("✅ MobileNet SSD loaded\n")
    except Exception as e:
        print(f"❌ Failed to load MobileNet SSD: {e}")
        system_status = "ERROR"
        return
    
    # COCO class labels for MobileNet SSD
    classes = ["background", "aeroplane", "bicycle", "bird", "boat", "bottle",
               "bus", "car", "cat", "chair", "cow", "diningtable", "dog", "horse",
               "motorbike", "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor"]
    
    # Initialize Camera
    print("📷 Initializing camera...")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ Failed to open camera")
        system_status = "ERROR"
        return
    
    # Optimize camera settings
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffering
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    print("✅ Camera initialized\n")
    
    # Start dedicated frame capture thread
    Thread(target=frame_capture_thread, args=(cap,), daemon=True).start()
    
    # Wait for first frame
    time.sleep(1)
    
    system_status = "ACTIVE"
    print("="*60)
    print("🛡️  VIGIL SYSTEM ACTIVE - Monitoring for threats...")
    print("="*60 + "\n")
    
    # Main detection loop
    while True:
        current_time = time.time()
        
        # Get latest frame from queue
        with frame_lock:
            if len(frame_queue) == 0:
                time.sleep(0.01)
                continue
            frame = frame_queue[-1].copy()  # Most recent frame
        
        # Reset status if no recent detections
        if current_time - last_detection_time > 10:
            last_intruder = "No intrusions yet"
            current_score = 0
            active_factors = []
        
        # Check for Arduino data
        if arduino and arduino.in_waiting:
            try:
                msg = arduino.readline().decode().strip()
                
                # Handle different message types
                if msg.startswith("DETECTION,"):
                    process_detection(msg, frame, net, classes, current_time)
                    
                elif msg.startswith("HEARTBEAT,"):
                    print(f"💓 Heartbeat: {msg}")
                    
                elif msg.startswith("SYSTEM,"):
                    print(f"📡 System: {msg}")
                    
            except UnicodeDecodeError:
                print("⚠️  Serial decode error - ignoring packet")
            except Exception as e:
                print(f"❌ Error processing serial data: {e}")
        
        # Small delay to prevent CPU saturation
        time.sleep(0.01)

# ============================================================================
# DETECTION PROCESSING
# ============================================================================

def process_detection(msg, frame, net, classes, current_time):
    """Process a DETECTION packet from Arduino"""
    global last_intruder, last_cx, last_cy, last_box_area, last_move_time
    global last_detection_time, last_notification_time
    global current_score, active_factors, total_detections, total_alerts
    
    try:
        # Parse telemetry packet
        parts = msg.split(",")
        arduino_conf = int(parts[1])
        arduino_dist = int(parts[2])
        arduino_time = int(parts[3])
        checksum = int(parts[4])
        
        # Validate checksum
        if not validate_checksum(arduino_conf, arduino_dist, arduino_time, checksum):
            print(f"⚠️  Checksum validation failed - discarding packet")
            return
        
        print(f"\n🔔 Hardware Trigger: Confidence={arduino_conf}, Distance={arduino_dist}cm")
        
    except (IndexError, ValueError) as e:
        print(f"⚠️  Malformed detection packet: {msg}")
        return
    
    # ========================================================================
    # STEP 1: OBJECT DETECTION (Verify it's a person)
    # ========================================================================
    
    blob = cv2.dnn.blobFromImage(
        cv2.resize(frame, (300, 300)),
        0.007843,
        (300, 300),
        127.5
    )
    net.setInput(blob)
    detections = net.forward()
    
    person_detected = False
    p_box = None
    person_confidence = 0
    
    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence > 0.5:
            idx = int(detections[0, 0, i, 1])
            if classes[idx] == "person":
                person_detected = True
                person_confidence = confidence
                p_box = detections[0, 0, i, 3:7] * np.array([
                    frame.shape[1], frame.shape[0], 
                    frame.shape[1], frame.shape[0]
                ])
                break
    
    if not person_detected:
        print("  ℹ️  No person detected in frame - likely false trigger")
        return
    
    print(f"  ✅ Person detected (confidence: {person_confidence:.2f})")
    
    # ========================================================================
    # STEP 2: THREAT SCORING ENGINE
    # ========================================================================
    
    total_detections += 1
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_detection_time = current_time
    
    # Initialize scoring
    threat_score = arduino_conf
    local_factors = []
    
    # --- Factor 1: Night Time (+30) ---
    hour = datetime.now().hour
    is_night = (hour >= NIGHT_START or hour < NIGHT_END)
    if is_night:
        threat_score += 30
        local_factors.append("NIGHT_TIME")
    
    # --- Factor 2: Near Boundary (+25) ---
    if 0 < arduino_dist < PROXIMITY_BOUNDARY:
        threat_score += 25
        local_factors.append("NEAR_BOUNDARY")
    
    # --- Factor 3: Fast Movement Detection (Enhanced with Z-Axis) ---
    (x1, y1, x2, y2) = p_box.astype("int")
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    box_area = (x2 - x1) * (y2 - y1)
    
    if last_cx != 0:  # Not first detection
        pixel_dist = ((cx - last_cx)**2 + (cy - last_cy)**2)**0.5
        time_delta = current_time - last_move_time
        
        # Calculate area growth (Z-axis movement)
        area_growth = 0
        if last_box_area > 0:
            area_growth = ((box_area - last_box_area) / last_box_area) * 100
        
        # Check both XY and Z axis movement
        if time_delta < MOVEMENT_TIME_WINDOW:
            
            # XY Plane (Lateral Movement)
            if pixel_dist > FAST_MOVEMENT_THRESHOLD_XY:
                threat_score += 20
                local_factors.append("FAST_MOVEMENT_LATERAL")
                print(f"  ⚡ Fast lateral movement detected: {pixel_dist:.1f} pixels in {time_delta:.1f}s")
            
            # Z Axis (Approaching Camera)
            elif area_growth > FAST_MOVEMENT_THRESHOLD_AREA:
                threat_score += 20
                local_factors.append("FAST_MOVEMENT_APPROACH")
                print(f"  🏃 Rapid approach detected: {area_growth:.1f}% size increase in {time_delta:.1f}s")
    
    # Update tracking state
    last_cx, last_cy = cx, cy
    last_box_area = box_area
    last_move_time = current_time
    
    # --- Factor 4: Facial Recognition (+40 Unknown / -60 Authorized) ---
    is_authorized = False
    detected_name = "Unknown"
    
    if FACE_REC_AVAILABLE:
        # Multi-Shot Voting: sample up to 3 frames to reduce false negatives
        # A single blurry/angled frame will no longer cause a missed identification
        attempts = 3
        for attempt in range(attempts):
            # Get the latest frame for each attempt
            with frame_lock:
                if len(frame_queue) == 0:
                    break
                sample_frame = frame_queue[-1].copy()

            enhanced_frame = enhance_for_recognition(sample_frame)
            face_locations = face_recognition.face_locations(enhanced_frame)
            face_encodings = face_recognition.face_encodings(
                enhanced_frame,
                face_locations,
                model='large'  # More accurate model
            )

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(
                    known_encodings,
                    face_encoding,
                    tolerance=FACE_RECOGNITION_TOLERANCE
                )
                if True in matches:
                    first_match_index = matches.index(True)
                    detected_name = known_names[first_match_index]
                    is_authorized = True
                    print(f"  Authorized user identified: {detected_name} (attempt {attempt+1}/{attempts})")
                    break

            if is_authorized:
                break  # No need to try again

            if attempt < attempts - 1:
                time.sleep(0.15)  # Brief pause between samples

        if not is_authorized:
            print(f"  Unknown entity (failed all {attempts} recognition attempts)")
    
    # Apply identity modifier
    if not is_authorized:
        threat_score += 40
        local_factors.append("UNKNOWN_ENTITY")
    else:
        threat_score -= 60  # Trust bonus
        local_factors.append("AUTHORIZED_USER")
    
    # ========================================================================
    # STEP 3: FINALIZE SCORE & UPDATE DASHBOARD
    # ========================================================================
    
    # Cap score between 0-100
    threat_score = max(0, min(threat_score, 100))
    
    # Update global state
    current_score = threat_score
    active_factors = local_factors
    
    # Generate status message
    if is_authorized:
        last_intruder = f"Authorized User: {detected_name} ({timestamp})"
        threat_level = "🟢 LOW"
    else:
        last_intruder = f"THREAT LEVEL {current_score}: {detected_name} ({timestamp})"
        if threat_score >= 80:
            threat_level = "🔴 CRITICAL"
        elif threat_score >= 60:
            threat_level = "🟠 HIGH"
        else:
            threat_level = "🟡 MEDIUM"
    
    print(f"\n{'='*60}")
    print(f"  {threat_level} THREAT SCORE: {threat_score}/100")
    print(f"  Identity: {detected_name}")
    print(f"  Factors: {', '.join(local_factors)}")
    print(f"{'='*60}\n")
    
    # ========================================================================
    # STEP 4: TRIGGER ALERT IF THRESHOLD EXCEEDED
    # ========================================================================
    
    dynamic_threshold = get_dynamic_threshold()
    
    if threat_score >= dynamic_threshold:
        # Check notification cooldown
        if current_time - last_notification_time > NOTIFICATION_COOLDOWN:
            
            print(f"🚨 ALERT TRIGGERED (Score {threat_score} ≥ Threshold {dynamic_threshold})")
            
            # Save snapshot
            filename = f"{IMAGE_DIR}/threat_{int(current_time)}_{threat_score}.jpg"
            
            # Draw bounding box on image
            alert_frame = frame.copy()
            cv2.rectangle(alert_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(alert_frame, f"THREAT: {threat_score}", (x1, y1-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
            cv2.imwrite(filename, alert_frame)
            print(f"  📸 Snapshot saved: {filename}")
            
            # Generate alert caption
            caption = generate_threat_report(
                threat_score,
                local_factors,
                arduino_dist,
                detected_name,
                arduino_conf
            )
            
            # Send Telegram alert
            if send_telegram_alert(filename, caption):
                total_alerts += 1
                last_notification_time = current_time
                print(f"  ✅ Alert sent to Telegram")
            else:
                print(f"  ⚠️  Failed to send alert")
        else:
            cooldown_remaining = NOTIFICATION_COOLDOWN - (current_time - last_notification_time)
            print(f"  ⏱️  Alert suppressed (cooldown: {cooldown_remaining:.1f}s remaining)")

# ============================================================================
# FLASK DASHBOARD
# ============================================================================

@app.route("/")
def dashboard():
    """Render main dashboard"""
    return render_template(
        "dashboard.html",
        event=last_intruder,
        score=current_score,
        factors=active_factors,
        status=system_status,
        detections=total_detections,
        alerts=total_alerts
    )

@app.route("/api/status")
def api_status():
    """API endpoint for real-time status updates"""
    return jsonify({
        "status": system_status,
        "score": current_score,
        "event": last_intruder,
        "factors": active_factors,
        "detections": total_detections,
        "alerts": total_alerts,
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/snapshot")
def api_snapshot():
    """Get current camera frame as JPEG"""
    global current_frame
    
    if current_frame is None:
        return "No frame available", 404
    
    with frame_lock:
        frame = current_frame.copy()
    
    # Encode as JPEG
    ret, buffer = cv2.imencode('.jpg', frame)
    
    from flask import Response
    return Response(
        buffer.tobytes(),
        mimetype='image/jpeg',
        headers={'Cache-Control': 'no-cache'}
    )

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Initialize and start VIGIL system"""
    
    print("\n" + "="*60)
    print("🛡️  VIGIL v2.0 - Intelligent Threat Detection System")
    print("="*60 + "\n")
    
    # Load facial recognition database
    load_known_faces()
    
    # Connect to Arduino
    if not connect_arduino():
        print("⚠️  WARNING: Continuing without Arduino connection")
        print("   System will not receive hardware triggers\n")
    
    # Start detection loop in background thread
    detection_thread = threading.Thread(target=detection_loop, daemon=True)
    detection_thread.start()
    
    print("🌐 Starting Flask dashboard on http://localhost:5000")
    print("   Press CTRL+C to stop\n")
    
    # Start Flask server
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down VIGIL system...")
        global capture_active
        capture_active = False
        if arduino:
            arduino.close()
        print("✅ System stopped\n")

if __name__ == "__main__":
    main()