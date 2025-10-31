#include <Wire.h>
#include <MPU6050.h>
#include <SoftwareSerial.h>
MPU6050 mpu;
SoftwareSerial BTSerial(10, 11); // RX, TX
void setup() {
  Serial.begin(9600);
  BTSerial.begin(9600);
  Wire.begin();
  mpu.initialize();
  if (!mpu.testConnection()) {
    Serial.println("MPU6050 failed");
    while(1);
  }
}
void loop() {
  int16_t ax, ay, az, gx, gy, gz;
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
  // Send CSV
  BTSerial.print(ax); BTSerial.print(",");
  BTSerial.print(ay); BTSerial.print(",");
  BTSerial.print(az); BTSerial.print(",");
  BTSerial.print(gx); BTSerial.print(",");
  BTSerial.print(gy); BTSerial.print(",");
  BTSerial.println(gz);
  delay(20); // 50Hz
}