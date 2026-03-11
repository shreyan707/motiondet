int pirPin = 4;

void setup() {
  pinMode(pirPin, INPUT);
  Serial.begin(9600);
}

void loop() {

  int motion = digitalRead(pirPin);

  if (motion == HIGH) {
    Serial.println("MOTION_DETECTED");
  }

  delay(500);

}