#define FW_VERSION "2026.11"
#define DEVICE_NAME "PEDALS"
#define SERIAL_BAUD 115200

#include <Joystick.h>
#include <EEPROM.h>
#include "HotasCommon.h"

const uint8_t RUDDER_PIN = A0;
const uint8_t RX_PIN = A1;
const uint8_t RY_PIN = A2;

enum AxisIndex {
  AX_RUDDER = 0,
  AX_RX = 1,
  AX_RY = 2,
  AXIS_COUNT = 3
};

const char* AXIS_NAMES[AXIS_COUNT] = {
  "RUDDER", "RX", "RY"
};

struct RudderCalibration {
  uint16_t minimum[AXIS_COUNT];
  uint16_t maximum[AXIS_COUNT];
  uint16_t magic;
};

struct SystemSettings {
  uint8_t inverted[AXIS_COUNT];
  float filters[2];
  uint16_t jitter;
  uint16_t deadzone[AXIS_COUNT];
  uint16_t magic;
};

RudderCalibration calibration;
SystemSettings settings;

const RudderCalibration DEFAULT_CALIBRATION = {
  {390, 453, 424},
  {600, 521, 509},
  0xCB11
};

const SystemSettings DEFAULT_SETTINGS = {
  {1, 1, 1},
  {0.30f, 0.20f},
  15,
  {0, 0, 0},
  0x212C
};

const int EEPROM_CALIBRATION = 0;
const int EEPROM_SETTINGS = 64;

Joystick_ Joystick(
  JOYSTICK_DEFAULT_REPORT_ID,
  JOYSTICK_TYPE_JOYSTICK,
  0,
  0,
  false, false, false,
  true, true, false,
  true, false, false,
  false, false
);

float filtered[AXIS_COUNT] = {0, 0, 0};
int lastOutput[AXIS_COUNT] = {0, 0, 0};
int output[AXIS_COUNT] = {0, 0, 0};
int rawValues[AXIS_COUNT] = {0, 0, 0};

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

void loadPersistentData() {
  EEPROM.get(EEPROM_CALIBRATION, calibration);

  if (calibration.magic != DEFAULT_CALIBRATION.magic) {
    calibration = DEFAULT_CALIBRATION;
    EEPROM.put(EEPROM_CALIBRATION, calibration);
  }

  EEPROM.get(EEPROM_SETTINGS, settings);

  if (settings.magic != DEFAULT_SETTINGS.magic) {
    settings = DEFAULT_SETTINGS;
    EEPROM.put(EEPROM_SETTINGS, settings);
  }
}

void saveCalibration() {
  calibration.magic = DEFAULT_CALIBRATION.magic;
  EEPROM.put(EEPROM_CALIBRATION, calibration);
}

void saveSettings() {
  settings.magic = DEFAULT_SETTINGS.magic;
  EEPROM.put(EEPROM_SETTINGS, settings);
}

void printIdentity() {
  Serial.print("ID|HFB|");
  Serial.print(DEVICE_NAME);
  Serial.print("|");
  Serial.print(FW_VERSION);
  Serial.print("|");
  Serial.println(HOTAS_PROTOCOL_VERSION);
}

void printSettings() {
  Serial.print("CFG|PEDALS|INV=");
  Serial.print(settings.inverted[0]);
  Serial.print(",");
  Serial.print(settings.inverted[1]);
  Serial.print(",");
  Serial.print(settings.inverted[2]);

  Serial.print("|FILTER=");
  Serial.print(settings.filters[0], 3);
  Serial.print(",");
  Serial.print(settings.filters[1], 3);

  Serial.print("|JITTER=");
  Serial.print(settings.jitter);

  Serial.print("|ATB=");

  Serial.print("|DZ=");
  Serial.print(settings.deadzone[0]);
  Serial.print(",");
  Serial.print(settings.deadzone[1]);
  Serial.print(",");
  Serial.println(settings.deadzone[2]);
}

void sendTelemetry() {
  if (!streamEnabled) return;

  unsigned long interval = 1000UL / max(1, streamRate);
  unsigned long now = millis();

  if (now - lastStream < interval) return;
  lastStream = now;

  Serial.print("DATA|PEDALS|");
  Serial.print(output[AX_RUDDER]);
  Serial.print("|");
  Serial.print(output[AX_RX]);
  Serial.print("|");
  Serial.println(output[AX_RY]);
}

void beginCalibrationAxis() {
  calibrationMin = rawValues[calibrationAxis];
  calibrationMax = rawValues[calibrationAxis];

  Serial.print("CAL|PEDALS|BEGIN|");
  Serial.println(AXIS_NAMES[calibrationAxis]);
}

void startCalibration() {
  calibrationActive = true;
  calibrationAxis = 0;
  beginCalibrationAxis();
}

void updateCalibration() {
  if (!calibrationActive) return;

  int raw = rawValues[calibrationAxis];

  if (raw < calibrationMin) calibrationMin = raw;
  if (raw > calibrationMax) calibrationMax = raw;

  unsigned long now = millis();

  if (now - lastCalibrationReport >= 250) {
    lastCalibrationReport = now;

    Serial.print("CAL|PEDALS|VALUE|");
    Serial.print(AXIS_NAMES[calibrationAxis]);
    Serial.print("|");
    Serial.print(calibrationMin);
    Serial.print("|");
    Serial.println(calibrationMax);
  }
}

void nextCalibrationAxis() {
  if (!calibrationActive) return;

  if (calibrationMax - calibrationMin < 5) {
    Serial.println("ERR|CALIBRATION_RANGE_TOO_SMALL");
    return;
  }

  calibration.minimum[calibrationAxis] =
    constrain(calibrationMin, 0L, 1023L);

  calibration.maximum[calibrationAxis] =
    constrain(calibrationMax, 0L, 1023L);

  calibrationAxis++;

  if (calibrationAxis >= AXIS_COUNT) {
    calibrationActive = false;
    saveCalibration();
    Serial.println("CAL|PEDALS|DONE");
    return;
  }

  beginCalibrationAxis();
}

void cancelCalibration() {
  if (!calibrationActive) return;

  calibrationActive = false;
  Serial.println("CAL|PEDALS|CANCELLED");
}

void processSetCommand(const String &command) {
  if (command.startsWith("SET INV ")) {
    String content = command.substring(8);
    int separator = content.lastIndexOf(' ');

    if (separator < 0) return;

    String axisName = content.substring(0, separator);
    int value = content.substring(separator + 1).toInt();
    int index = axisIndexByName(axisName);

    if (index < 0) {
      Serial.println("ERR|UNKNOWN_AXIS");
      return;
    }

    settings.inverted[index] = value ? 1 : 0;
    saveSettings();
    Serial.println("ACK|SET_INV");
    printSettings();
    return;
  }

  if (command.startsWith("SET DZ ")) {
    String content = command.substring(7);
    int separator = content.lastIndexOf(' ');

    if (separator < 0) return;

    String axisName = content.substring(0, separator);
    long value = content.substring(separator + 1).toInt();
    int index = axisIndexByName(axisName);

    if (index < 0) {
      Serial.println("ERR|UNKNOWN_AXIS");
      return;
    }

    settings.deadzone[index] = clampDeadzone(value);
    saveSettings();
    Serial.println("ACK|SET_DZ");
    printSettings();
    return;
  }

  if (command.startsWith("SET FILTER ")) {
    String content = command.substring(11);
    int separator = content.indexOf(' ');

    if (separator < 0) return;

    int number = content.substring(0, separator).toInt();
    float value = content.substring(separator + 1).toFloat();

    if (number < 1 || number > 2) {
      Serial.println("ERR|UNKNOWN_FILTER");
      return;
    }

    settings.filters[number - 1] = clampAlpha(value);
    saveSettings();
    Serial.println("ACK|SET_FILTER");
    printSettings();
    return;
  }

  if (command.startsWith("SET JITTER ")) {
    long value = command.substring(11).toInt();
    settings.jitter = clampJitter(value);
    saveSettings();
    Serial.println("ACK|SET_JITTER");
    printSettings();
  }
}

void processCommand(String command) {
  command.trim();
  command.toUpperCase();

  if (command == "IDENT") {
    printIdentity();
  } else if (command == "GET SETTINGS") {
    printSettings();
  } else if (command == "STATUS") {
    printIdentity();
    printSettings();
  } else if (command == "STREAM 1") {
    streamEnabled = true;
    Serial.println("ACK|STREAM_ON");
  } else if (command == "STREAM 0") {
    streamEnabled = false;
    Serial.println("ACK|STREAM_OFF");
  } else if (command.startsWith("RATE ")) {
    streamRate = constrain(
      command.substring(5).toInt(),
      1,
      60
    );
    Serial.println("ACK|RATE");
  } else if (command == "CAL START") {
    startCalibration();
  } else if (command == "CAL NEXT") {
    nextCalibrationAxis();
  } else if (command == "CAL CANCEL") {
    cancelCalibration();
  } else if (command.startsWith("SET ")) {
    processSetCommand(command);
  } else {
    Serial.println("ERR|UNKNOWN_COMMAND");
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);

  loadPersistentData();

  Joystick.setRudderRange(
    HOTAS_AXIS_MIN,
    HOTAS_AXIS_MAX
  );
  Joystick.setRxAxisRange(
    HOTAS_AXIS_MIN,
    HOTAS_AXIS_MAX
  );
  Joystick.setRyAxisRange(
    HOTAS_AXIS_MIN,
    HOTAS_AXIS_MAX
  );

  Joystick.begin(false);

  for (int i = 0; i < AXIS_COUNT; i++) {
    rawValues[i] = analogRead(
      i == 0 ? RUDDER_PIN :
      i == 1 ? RX_PIN :
               RY_PIN
    );

    filtered[i] = rawValues[i];
  }
}

void loop() {
  while (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    processCommand(command);
  }

  rawValues[AX_RUDDER] = analogRead(RUDDER_PIN);
  rawValues[AX_RX] = analogRead(RX_PIN);
  rawValues[AX_RY] = analogRead(RY_PIN);

  applyAdaptiveEMA(
    rawValues[AX_RUDDER],
    filtered[AX_RUDDER],
    settings.filters[0],
    0
  );

  applyAdaptiveEMA(
    rawValues[AX_RX],
    filtered[AX_RX],
    settings.filters[1],
    0
  );

  applyAdaptiveEMA(
    rawValues[AX_RY],
    filtered[AX_RY],
    settings.filters[1],
    0
  );

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

  Joystick.setRudder(output[AX_RUDDER]);
  Joystick.setRxAxis(output[AX_RX]);
  Joystick.setRyAxis(output[AX_RY]);
  Joystick.sendState();

  updateCalibration();
  sendTelemetry();

  delay(3);
}
