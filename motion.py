import cv2
import serial
import time
import numpy as np

arduino = serial.Serial('COM8',9600)

net = cv2.dnn.readNetFromCaffe(
    "MobileNetSSD_deploy.prototxt",
    "MobileNetSSD_deploy.caffemodel"
)

classes = ["background","aeroplane","bicycle","bird","boat","bottle",
           "bus","car","cat","chair","cow","diningtable","dog","horse",
           "motorbike","person","pottedplant","sheep","sofa","train","tvmonitor"]

cap = cv2.VideoCapture(0)

while True:

    ret, frame = cap.read()
    if not ret:
        continue

    if arduino.in_waiting:

        msg = arduino.readline().decode().strip()

        if msg == "MOTION_DETECTED":

            print("Motion Triggered")

            h,w = frame.shape[:2]

            blob = cv2.dnn.blobFromImage(
                cv2.resize(frame,(300,300)),
                0.007843,
                (300,300),
                127.5
            )

            net.setInput(blob)
            detections = net.forward()

            intruder = False

            for i in range(detections.shape[2]):

                confidence = detections[0,0,i,2]

                if confidence > 0.5:

                    idx = int(detections[0,0,i,1])

                    if classes[idx] == "person":

                        intruder = True

                        box = detections[0,0,i,3:7] * np.array([w,h,w,h])
                        (x1,y1,x2,y2) = box.astype("int")

                        cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)

            if intruder:

                print("INTRUDER DETECTED")

                filename = f"intruder_{int(time.time())}.jpg"
                cv2.imwrite(filename,frame)

                cv2.imshow("Intruder",frame)
                cv2.waitKey(500)