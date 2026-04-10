# VIGIL: Intelligent Multi-Sensor Fusion & Threat Scoring System

## 1. Project Overview
VIGIL is an advanced, multi-tiered intrusion detection system that upgrades traditional binary alarm mechanisms (e.g., "motion detected") into a context-aware **Intelligent Threat Scoring Engine**. 

Rather than sending an alert every time a leaf blows or a resident walks to the kitchen at night, VIGIL fuses hardware sensor telemetry (PIR, Ultrasonic, Acoustic) with computer vision and biometric facial recognition. It calculates a dynamic **Threat Score (0-100)** to determine whether an event constitutes a genuine security risk.

---

## 2. System Architecture

The architecture is split into three primary layers: Hardware (Edge Sensing), Logic (AI & Scoring), and Interface (Dashboard & Alerts).

### A. Hardware Sensors (Arduino)
An Arduino microcontroller continually parses environmental changes.
- **PIR Sensor (Pin 4):** Primary infrared motion detection (Weight: +50).
- **Ultrasonic Sensor (HC-SR04, Pins 5/6):** Depth perception and proximity validation (Weight: +30 if distance < 70cm).
- **Sound Sensor (KY-038, Pin 7):** Acoustic disruption detection (Weight: +20).

**Data Pipeline:** The Arduino aggregates these inputs into a *Fusion Confidence Score*. If the confidence exceeds the threshold (45), it transmits telemetry via Serial over USB in the format: `DETECTION,<confidence>,<distance>`.

### B. Logic & AI Engine (Python `notifbot.py`)
The backend Python daemon waits for the hardware trigger. Once triggered, it captures a video frame and processes it via:
1. **Object Detection:** OpenCV with MobileNetSSD (`.caffemodel`) ensures the trigger was caused by a *person* (confidence > 0.5), not a pet or shadow.
2. **Biometric Identification:** `face_recognition` maps the face to authorized users in the `/known_faces/` directory.
3. **Threat Scoring Engine:** Synthesizes context to generate the final Threat Score (capped 0-100).
   - **Base Score:** Uses the Arduino's fusion confidence (e.g., 50, 70).
   - **Temporal Context:** +30 points if it is nighttime (10:00 PM – 6:00 AM).
   - **Proximity:** +25 points if the subject is "Near Boundary" (Ultrasonic distance < 100cm).
   - **Velocity/Behavior:** +20 points for "Fast Movement" based on 2D pixel delta tracking between frames (>80 pixels).
   - **Identity Modifier:** +40 points for Unknown Entities; **-60 points** (Trust Bonus) if an Authorized User is recognized.

### C. Interface Layer
- **Telegram Bot Integration:** Sends an immediate photo capture and threat breakdown to a registered Telegram chat if the final Threat Score ≥ 60.
- **Glassmorphic VIGIL Dashboard:** A Flask-served web UI (`http://localhost:5000`) functioning as a local Node monitor, boasting real-time status shifts, threat meters, and active factor tags.

---

For the facial recognition, we are using the face_recognition library (built on top of dlib and ResNet-34).

Here is exactly how it works in your project:
Encoder: It uses a Deep Learning model to turn a human face into 128 unique numbers (measurements of facial features).
Comparison: Every time the system detects a person, it compares those 128 numbers against the faces stored in your known_faces folder.
Threshold (Tolerance): It checks if the "distance" (difference) between the new face and your saved face is low enough to be a match.

## 3. Testing Methodology
The system was validated using a Simulated Intrusion Protocol (SIP).

| Scenario | Variables | Expected Outcome | System Result |
| :--- | :--- | :--- | :--- |
| **Authorized Entry (Day)** | Known Face, Day Time, Normal Speed | **Score < 40** (No Alert) | **PASS** (Trust Bonus negated Base) |
| **Intruder (Night)** | Unknown Face, 3:00 AM | **Score > 80** (Telegram Alert) | **PASS** (+30 Night, +40 Unknown) |
| **Fast Intruder (Day)** | Unknown Face, Fast sprint to camera | **Score > 60** (Telegram Alert) | **PASS** (+20 Fast, +40 Unknown) |
| **Authorized Entry (Night)** | Known Face, 2:00 AM | **Score < 60** (Monitored, No Alert) | **PASS** (+30 Night, -60 Trust) |

---

## 4. ⚠️ CRITICAL SYSTEM LIMITATIONS ⚠️
*As vivid and accurate as possible, these are the fundamental vulnerabilities and edge cases of the current VIGIL implementation:*

### I. The "Z-Axis" Velocity Blindspot
The "Fast Movement" (+20) factor calculates speed based on 2D pixel drift (X/Y axis change of the bounding box center). **If an intruder sprints directly head-on at the camera lens**, the center of their bounding box barely drifts. They only increase in scale. The system will fail to flag this as "Fast Movement."

### II. Hardware Bottlenecks and Polling Desync
The Arduino enforces a massive `delay(5000)` (5 seconds) after sending a detection trigger to prevent serial flooding. 
- **The Exploit:** If an authorized user walks past the camera, the system triggers, identifies them, lowers the score, and enters a 5-second sleep cycle. If an actual intruder immediately follows 1 second behind them, the Arduino is "asleep" and the Python backend will not capture the second entity until the cooldown ends.

### III. Biometric Lighting Vulnerability
The `face_recognition` library requires high-contrast, well-lit facial data. At night or in low-light environments, authorized users might fail identification.
- **The Result:** The system defaults to "UNKNOWN_ENTITY," applies the +40 penalty, processes the +30 Night Time penalty, and immediately triggers a False Positive "CRITICAL THREAT" alarm on an authorized resident.

### IV. Mathematical Override Edge-Case
The Trust Bonus is `-60`. If the Arduino Base Confidence is extremely high (e.g., 100), and an authorized user runs (Fast Movement +20) near the boundary (Near Boundary +25) at night (Night Time +30):
`100 (Base) + 30 (Night) + 25 (Near) + 20 (Fast) - 60 (Trust) = 115`.
Even with the cap, the score evaluates to **100**. This means **an authorized user acting erratically at night will still trigger the alarm.** (Which is arguably a feature, but potentially a frustrating false positive limitation of rigid addition/subtraction models).

### V. CPU Blocking Operations
The `detection_loop()` in Python executes sequentially on the CPU. The MobileNetSSD inference combined with `face_recognition.face_encodings` takes considerable processing time. While processing Frame A, Frame B and C are dropped. Fast intruders might vanish from the frame by the time the camera buffer processes.

---

## 5. Future Scope & Roadmap
To mitigate current limits and scale properly:
1. **Threaded Video Capture:** Move OpenCV frame reading to a dedicated daemon thread to prevent processing lag from blocking frame ingestion.
2. **Infrared (IR) Cameras:** Utilize an IR module for the webcam to enable near-perfect Face Recognition in the dark, solving the nighttime False Positive vulnerability.
3. **Bounding Box Scaling Logic:** Modify the velocity tracker to consider Area `(w * h)` growth over time to detect objects moving parallel to the Z-axis (approaching the camera directly).
4. **Transition to Asynchronous I/O:** Remove the `delay(5000)` on the Arduino and utilize `millis()`-based non-blocking timers to track cooldowns, allowing the system to rapidly interpret consecutive events.
