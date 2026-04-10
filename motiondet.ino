const int PIR_PIN = 4;
const int TRIG_PIN = 5;
const int ECHO_PIN = 6;
const int SOUND_PIN = 7;

const int THRESHOLD = 45;
const int PROXIMITY_LIMIT = 100;

unsigned long lastTriggerTime = 0;
const unsigned long COOLDOWN_PERIOD = 5000;

const unsigned long SENSOR_WARMUP = 2000;
unsigned long bootTime = 0;

int consecutiveDetections = 0;
const int DETECTION_CONFIRM = 2;

void setup() {
  pinMode(PIR_PIN, INPUT);
  pinMode(SOUND_PIN, INPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  
  Serial.begin(9600);
  
  bootTime = millis();
  
  Serial.println("SYSTEM,ONLINE,VIGIL_V2");
}

void loop() {
  unsigned long currentTime = millis();
  
  if (currentTime - bootTime < SENSOR_WARMUP) {
    delay(100);
    return;
  }
  
  int confidence = 0;
  
  bool pirActive = digitalRead(PIR_PIN) == HIGH;
  if (pirActive) {
    confidence += 50;
  }
  
  bool soundActive = digitalRead(SOUND_PIN) == HIGH;
  if (soundActive) {
    confidence += 20;
  }
  
  long distance = getDistance();
  bool proximityActive = (distance > 0 && distance < PROXIMITY_LIMIT);
  if (proximityActive) {
    confidence += 30;
  }
  
  if (confidence >= THRESHOLD) {
    consecutiveDetections++;
    
    if (consecutiveDetections >= DETECTION_CONFIRM) {
      
      if (currentTime - lastTriggerTime >= COOLDOWN_PERIOD) {
        
        sendDetectionPacket(confidence, distance, currentTime);
        
        lastTriggerTime = currentTime;
        
        consecutiveDetections = 0;
      }
    }
  } else {
    consecutiveDetections = 0;
  }
  
  delay(50);
}

long getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  
  if (duration == 0) {
    return -1;
  }
  
  long distance = (duration / 2) / 29.1;
  
  if (distance < 2 || distance > 400) {
    return -1;
  }
  
  return distance;
}

void sendDetectionPacket(int confidence, long distance, unsigned long timestamp) {
  int checksum = (confidence + distance + (timestamp % 1000)) % 256;
  
  Serial.print("DETECTION,");
  Serial.print(confidence);
  Serial.print(",");
  Serial.print(distance);
  Serial.print(",");
  Serial.print(timestamp);
  Serial.print(",");
  Serial.println(checksum);
}

void sendHeartbeat() {
  static unsigned long lastHeartbeat = 0;
  unsigned long currentTime = millis();
  
  if (currentTime - lastHeartbeat > 30000) {
    Serial.print("HEARTBEAT,");
    Serial.print(currentTime);
    Serial.print(",");
    Serial.print(digitalRead(PIR_PIN));
    Serial.print(",");
    Serial.print(digitalRead(SOUND_PIN));
    Serial.print(",");
    Serial.println(getDistance());
    
    lastHeartbeat = currentTime;
  }
}