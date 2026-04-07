// --- Multi-Sensor Fusion Settings (MotionDet) ---
const int PIR_PIN = 4;
const int TRIG_PIN = 5;
const int ECHO_PIN = 6;
const int SOUND_PIN = 7;

const int THRESHOLD = 65;         // Overall confidence threshold
const int PROXIMITY_LIMIT = 150;  // Detection range (cm)

void setup() {
  pinMode(PIR_PIN, INPUT);
  pinMode(SOUND_PIN, INPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  
  Serial.begin(9600);
  delay(2000); // Allow sensor stabilization
}

void loop() {
  int confidence = 0;

  // 1. PIR (Motion) - Weight 50
  if (digitalRead(PIR_PIN) == HIGH) {
    confidence += 50;
  }

  // 2. Sound (KY-038) - Weight 20
  if (digitalRead(SOUND_PIN) == HIGH) {
    confidence += 20;
  }

  // 3. Ultrasonic (Proximity) - Weight 30
  long distance = getDistance();
  if (distance > 0 && distance < PROXIMITY_LIMIT) {
    confidence += 30;
  }

  // --- Fusion Logic Trigger ---
  if (confidence >= THRESHOLD) {
    // Send detailed telemetry for the Threat Scoring Engine
    Serial.print("DETECTION,");
    Serial.print(confidence);
    Serial.print(",");
    Serial.println(distance);
    
    // Cooldown interval (5 seconds)
    delay(5000); 
  } else {
    // Sampling stabilization delay
    delay(200);
  }
}

long getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // 30ms timeout
  if (duration == 0) return -1;
  
  return (duration / 2) / 29.1;
}