#define FW_VERSION "2026.11"
#define DEVICE_NAME "THROTTLE"
#define SERIAL_BAUD 115200

#include <Wire.h>
#include <PCF8575.h>
#include <Joystick.h>
#include <ADS1X15.h>
#include <EEPROM.h>
#include "HotasCommon.h"

#define NUM_BUTTONS 31
#define PCF1_ADDRESS 0x21
#define PCF2_ADDRESS 0x20

enum AxisIndex {
  AX_X = 0,
  AX_Y,
  AX_Z,
  AX_RX,
  AX_RY,
  AX_RZ,
  AXIS_COUNT
};

const char* AXIS_NAMES[AXIS_COUNT] = {
  "X", "Y", "Z", "RX", "RY", "RZ"
};

struct ThrottleCalibration {
  uint16_t minimum[AXIS_COUNT];
  uint16_t maximum[AXIS_COUNT];
  uint16_t magic;
};

struct SystemSettings {
  uint8_t inverted[AXIS_COUNT];
  float filters[2];
  uint8_t atb;
  uint16_t jitter;
  uint16_t deadzone[AXIS_COUNT];
  uint16_t magic;
};

const ThrottleCalibration DEFAULT_CALIBRATION = {
  {0, 0, 0, 13350, 12700, 11080},
  {1023, 1023, 26000, 21350, 21850, 23500},
  0xCB12
};

const SystemSettings DEFAULT_SETTINGS = {
  {0, 0, 0, 0, 0, 0},
  {0.35f, 0.15f},
  0,
  15,
  {0, 0, 0, 0, 0, 0},
  0x212A
};

ThrottleCalibration calibration;
SystemSettings settings;

const int EEPROM_CALIBRATION = 0;
const int EEPROM_SETTINGS = 64;

PCF8575 pcf1(PCF1_ADDRESS);
PCF8575 pcf2(PCF2_ADDRESS);
ADS1115 ads(0x4A);

Joystick_ Joystick(
  JOYSTICK_DEFAULT_REPORT_ID,
  JOYSTICK_TYPE_JOYSTICK,
  NUM_BUTTONS,
  1,
  true, true, true,
  true, true, true,
  false, false,
  false, false, false
);

float filtered[AXIS_COUNT] = {0};
long rawValues[AXIS_COUNT] = {0};
int output[AXIS_COUNT] = {0};
int lastOutput[AXIS_COUNT] = {0};

uint32_t buttonMask = 0;
int hatValue = -1;

bool streamEnabled = false;
uint8_t streamRate = 30;
unsigned long lastStream = 0;

bool calibrationActive = false;
uint8_t calibrationAxis = 0;
long calibrationMin = 0;
long calibrationMax = 0;
unsigned long lastCalibrationReport = 0;

int axisIndexByName(String name) {
  name.trim();
  name.toUpperCase();

  for (int i = 0; i < AXIS_COUNT; i++) {
    if (name == AXIS_NAMES[i]) return i;
  }

  return -1;
}

void saveCalibration() {
  calibration.magic = DEFAULT_CALIBRATION.magic;
  EEPROM.put(EEPROM_CALIBRATION, calibration);
}

void saveSettings() {
  settings.magic = DEFAULT_SETTINGS.magic;
  EEPROM.put(EEPROM_SETTINGS, settings);
}

void loadPersistentData() {
  EEPROM.get(EEPROM_CALIBRATION, calibration);

  if (calibration.magic != DEFAULT_CALIBRATION.magic) {
    calibration = DEFAULT_CALIBRATION;
    saveCalibration();
  }

  EEPROM.get(EEPROM_SETTINGS, settings);

  if (settings.magic != DEFAULT_SETTINGS.magic) {
    settings = DEFAULT_SETTINGS;
    saveSettings();
  }
}

void printIdentity() {
  Serial.print("ID|HFB|THROTTLE|");
  Serial.print(FW_VERSION);
  Serial.print("|");
  Serial.println(HOTAS_PROTOCOL_VERSION);
}

void printSettings() {
  Serial.print("CFG|THROTTLE|INV=");

  for (int i = 0; i < AXIS_COUNT; i++) {
    if (i) Serial.print(",");
    Serial.print(settings.inverted[i]);
  }

  Serial.print("|FILTER=");
  Serial.print(settings.filters[0], 3);
  Serial.print(",");
  Serial.print(settings.filters[1], 3);

  Serial.print("|JITTER=");
  Serial.print(settings.jitter);

  Serial.print("|ATB=");
  Serial.print(settings.atb);

  Serial.print("|DZ=");

  for (int i = 0; i < AXIS_COUNT; i++) {
    if (i) Serial.print(",");
    Serial.print(settings.deadzone[i]);
  }

  Serial.println();
}

void readHardware() {
  rawValues[AX_X] = analogRead(A0);
  rawValues[AX_Y] = analogRead(A1);
  rawValues[AX_Z] = ads.readADC(0);
  rawValues[AX_RX] = ads.readADC(1);
  rawValues[AX_RY] = ads.readADC(2);
  rawValues[AX_RZ] = ads.readADC(3);
}

void readButtons() {
  uint16_t first = pcf1.read16();
  uint16_t second = pcf2.read16();

  buttonMask = 0;

  for (int i = 0; i < 16; i++) {
    bool pressed = !((first >> i) & 1);

    Joystick.setButton(i, pressed);

    if (pressed) buttonMask |= (1UL << i);
  }

  for (int i = 0; i < 15; i++) {
    bool pressed = !((second >> i) & 1);
    int index = i + 16;

    Joystick.setButton(index, pressed);

    if (pressed) buttonMask |= (1UL << index);
  }
}

void processAxes() {
  applyAdaptiveEMA(
    rawValues[AX_X],
    filtered[AX_X],
    settings.filters[0],
    0
  );

  applyAdaptiveEMA(
    rawValues[AX_Y],
    filtered[AX_Y],
    settings.filters[0],
    0
  );

  for (int i = AX_Z; i < AXIS_COUNT; i++) {
    applyAdaptiveEMA(
      rawValues[i],
      filtered[i],
      settings.filters[1],
      3
    );
  }

  for (int i = 0; i < AXIS_COUNT; i++) {
    int value = applyAxisProcessing(
      filtered[i],
      calibration.minimum[i],
      calibration.maximum[i],
      settings.deadzone[i],
      settings.inverted[i]
    );

    output[i] = applyHysteresis(
      value,
      lastOutput[i],
      settings.jitter
    );
  }

  if (settings.atb) {
    bool up = output[AX_Y] < -8000;
    bool down = output[AX_Y] > 8000;
    bool right = output[AX_X] > 8000;
    bool left = output[AX_X] < -8000;

    hatValue = -1;

    if (up && !left && !right) hatValue = 0;
    else if (up && right) hatValue = 45;
    else if (right && !up && !down) hatValue = 90;
    else if (down && right) hatValue = 135;
    else if (down && !left && !right) hatValue = 180;
    else if (down && left) hatValue = 225;
    else if (left && !up && !down) hatValue = 270;
    else if (up && left) hatValue = 315;

    Joystick.setHatSwitch(0, hatValue);
    Joystick.setXAxis(0);
    Joystick.setYAxis(0);
  } else {
    hatValue = -1;

    Joystick.setHatSwitch(0, -1);
    Joystick.setXAxis(output[AX_X]);
    Joystick.setYAxis(output[AX_Y]);
  }

  Joystick.setZAxis(output[AX_Z]);
  Joystick.setRxAxis(output[AX_RX]);
  Joystick.setRyAxis(output[AX_RY]);
  Joystick.setRzAxis(output[AX_RZ]);
}

void sendTelemetry() {
  if (!streamEnabled) return;

  unsigned long interval = 1000UL / max(1, streamRate);
  unsigned long now = millis();

  if (now - lastStream < interval) return;
  lastStream = now;

  Serial.print("DATA|THROTTLE");

  for (int i = 0; i < AXIS_COUNT; i++) {
    Serial.print("|");
    Serial.print(output[i]);
  }

  Serial.print("|");
  Serial.print(hatValue);
  Serial.print("|");
  Serial.println(buttonMask, HEX);
}

void beginCalibrationAxis() {
  calibrationMin = rawValues[calibrationAxis];
  calibrationMax = rawValues[calibrationAxis];

  Serial.print("CAL|THROTTLE|BEGIN|");
  Serial.println(AXIS_NAMES[calibrationAxis]);
}

void startCalibration() {
  calibrationActive = true;
  calibrationAxis = 0;
  beginCalibrationAxis();
}

void updateCalibration() {
  if (!calibrationActive) return;

  long value = rawValues[calibrationAxis];

  calibrationMin = min(calibrationMin, value);
  calibrationMax = max(calibrationMax, value);

  if (millis() - lastCalibrationReport >= 250) {
    lastCalibrationReport = millis();

    Serial.print("CAL|THROTTLE|VALUE|");
    Serial.print(AXIS_NAMES[calibrationAxis]);
    Serial.print("|");
    Serial.print(calibrationMin);
    Serial.print("|");
    Serial.println(calibrationMax);
  }
}

void nextCalibrationAxis() {
  if (!calibrationActive) return;

  long requiredRange =
    calibrationAxis < 2 ? 5 : 50;

  if (calibrationMax - calibrationMin < requiredRange) {
    Serial.println("ERR|CALIBRATION_RANGE_TOO_SMALL");
    return;
  }

  calibration.minimum[calibrationAxis] =
    constrain(calibrationMin, 0L, 65535L);

  calibration.maximum[calibrationAxis] =
    constrain(calibrationMax, 0L, 65535L);

  calibrationAxis++;

  if (calibrationAxis >= AXIS_COUNT) {
    calibrationActive = false;
    saveCalibration();
    Serial.println("CAL|THROTTLE|DONE");
  } else {
    beginCalibrationAxis();
  }
}

void processSetCommand(String command) {
  if (command.startsWith("SET INV ")) {
    String content = command.substring(8);
    int separator = content.lastIndexOf(' ');

    String axis = content.substring(0, separator);
    int index = axisIndexByName(axis);

    if (index < 0) {
      Serial.println("ERR|UNKNOWN_AXIS");
      return;
    }

    settings.inverted[index] =
      content.substring(separator + 1).toInt() ? 1 : 0;

  } else if (command.startsWith("SET DZ ")) {
    String content = command.substring(7);
    int separator = content.lastIndexOf(' ');

    int index = axisIndexByName(
      content.substring(0, separator)
    );

    if (index < 0) {
      Serial.println("ERR|UNKNOWN_AXIS");
      return;
    }

    settings.deadzone[index] = clampDeadzone(
      content.substring(separator + 1).toInt()
    );

  } else if (command.startsWith("SET FILTER ")) {
    String content = command.substring(11);
    int separator = content.indexOf(' ');

    int number = content.substring(0, separator).toInt();
    float value = content.substring(separator + 1).toFloat();

    if (number < 1 || number > 2) {
      Serial.println("ERR|UNKNOWN_FILTER");
      return;
    }

    settings.filters[number - 1] = clampAlpha(value);

  } else if (command.startsWith("SET JITTER ")) {
    settings.jitter = clampJitter(
      command.substring(11).toInt()
    );

  } else if (command.startsWith("SET ATB ")) {
    String content = command.substring(8);
    int separator = content.indexOf(' ');

    int number = content.substring(0, separator).toInt();

    if (number != 1) {
      Serial.println("ERR|UNKNOWN_ATB");
      return;
    }

    settings.atb =
      content.substring(separator + 1).toInt() ? 1 : 0;

  } else {
    Serial.println("ERR|UNKNOWN_SET_COMMAND");
    return;
  }

  saveSettings();
  Serial.println("ACK|SET");
  printSettings();
}

void processCommand(String command) {
  command.trim();
  command.toUpperCase();

  if (command == "IDENT") printIdentity();
  else if (command == "GET SETTINGS") printSettings();
  else if (command == "STATUS") {
    printIdentity();
    printSettings();
  }
  else if (command == "STREAM 1") streamEnabled = true;
  else if (command == "STREAM 0") streamEnabled = false;
  else if (command.startsWith("RATE ")) {
    streamRate = constrain(command.substring(5).toInt(), 1, 60);
  }
  else if (command == "CAL START") startCalibration();
  else if (command == "CAL NEXT") nextCalibrationAxis();
  else if (command == "CAL CANCEL") {
    calibrationActive = false;
    Serial.println("CAL|THROTTLE|CANCELLED");
  }
  else if (command.startsWith("SET ")) processSetCommand(command);
  else Serial.println("ERR|UNKNOWN_COMMAND");
}

void setup() {
  Serial.begin(SERIAL_BAUD);

  Wire.begin();
  Wire.setClock(400000);

  ads.begin();
  ads.setGain(1);
  ads.setDataRate(7);

  pcf1.begin();
  pcf2.begin();
  pcf1.setButtonMask(0xFFFF);
  pcf2.setButtonMask(0xFFFF);

  loadPersistentData();
  readHardware();

  for (int i = 0; i < AXIS_COUNT; i++) {
    filtered[i] = rawValues[i];
  }

  Joystick.setXAxisRange(HOTAS_AXIS_MIN, HOTAS_AXIS_MAX);
  Joystick.setYAxisRange(HOTAS_AXIS_MIN, HOTAS_AXIS_MAX);
  Joystick.setZAxisRange(HOTAS_AXIS_MIN, HOTAS_AXIS_MAX);
  Joystick.setRxAxisRange(HOTAS_AXIS_MIN, HOTAS_AXIS_MAX);
  Joystick.setRyAxisRange(HOTAS_AXIS_MIN, HOTAS_AXIS_MAX);
  Joystick.setRzAxisRange(HOTAS_AXIS_MIN, HOTAS_AXIS_MAX);

  Joystick.begin(false);
}

void loop() {
  while (Serial.available()) {
    processCommand(Serial.readStringUntil('\n'));
  }

  readHardware();
  readButtons();
  processAxes();

  Joystick.sendState();

  updateCalibration();
  sendTelemetry();

  delay(3);
}
