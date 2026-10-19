#define FW_VERSION "2026.11"
#define DEVICE_NAME "STICK"
#define SERIAL_BAUD 115200

#include <Wire.h>
#include <PCF8575.h>
#include <Joystick.h>
#include <ADS1X15.h>
#include <EEPROM.h>
#include "HotasCommon.h"

#define NUM_BUTTONS 28
#define PCF1_ADDRESS 0x20
#define PCF2_ADDRESS 0x21
#define AT24_ADDRESS 0x50
#define AT24_PAGE_SIZE 32
#define LED_ATB_PIN 5

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

struct GimbalCalibration {
  uint16_t xMin;
  uint16_t xMax;
  uint16_t yMin;
  uint16_t yMax;
  uint16_t magic;
};

struct GripCalibration {
  uint16_t minimum[4];
  uint16_t maximum[4];
  uint16_t magic;
};

struct SystemSettings {
  uint8_t inverted[AXIS_COUNT];
  float filters[2];
  uint8_t atb[2];
  uint16_t jitter;
  uint16_t deadzone[AXIS_COUNT];
  uint16_t magic;
};

const GimbalCalibration DEFAULT_GIMBAL = {
  9700, 17000,
  9000, 15850,
  0xAB11
};

const GripCalibration DEFAULT_GRIP = {
  {7350, 0, 0, 13000},
  {8755, 32767, 32767, 22500},
  0x5611
};

const SystemSettings DEFAULT_SETTINGS = {
  {0, 1, 0, 0, 0, 1},
  {0.35f, 0.15f},
  {0, 0},
  15,
  {0, 0, 0, 0, 0, 0},
  0x2125
};

GimbalCalibration gimbalCalibration;
GripCalibration gripCalibration;
SystemSettings settings;

const int EEPROM_GIMBAL = 0;
const int EEPROM_SETTINGS = 64;

PCF8575 pcf1(PCF1_ADDRESS);
PCF8575 pcf2(PCF2_ADDRESS);

ADS1115 adsGrip(0x48);
ADS1115 adsGimbal(0x49);

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

bool at24Present = false;

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

bool at24Write(
  uint16_t address,
  const uint8_t* data,
  uint16_t length
) {
  uint16_t written = 0;

  while (written < length) {
    uint16_t pageSpace =
      AT24_PAGE_SIZE - (address % AT24_PAGE_SIZE);

    uint16_t block = min(
      pageSpace,
      (uint16_t)(length - written)
    );

    Wire.beginTransmission(AT24_ADDRESS);
    Wire.write(address >> 8);
    Wire.write(address & 0xFF);

    for (uint16_t i = 0; i < block; i++) {
      Wire.write(data[written + i]);
    }

    if (Wire.endTransmission() != 0) return false;

    delay(6);

    address += block;
    written += block;
  }

  return true;
}

bool at24Read(
  uint16_t address,
  uint8_t* data,
  uint16_t length
) {
  uint16_t readCount = 0;

  while (readCount < length) {
    uint16_t block = min(
      (uint16_t)32,
      (uint16_t)(length - readCount)
    );

    Wire.beginTransmission(AT24_ADDRESS);
    Wire.write(address >> 8);
    Wire.write(address & 0xFF);

    if (Wire.endTransmission(false) != 0) return false;

    Wire.requestFrom(AT24_ADDRESS, block);

    uint16_t index = 0;

    while (Wire.available() && index < block) {
      data[readCount + index] = Wire.read();
      index++;
    }

    if (index != block) return false;

    address += block;
    readCount += block;
  }

  return true;
}

void saveGripCalibration() {
  if (!at24Present) return;

  gripCalibration.magic = DEFAULT_GRIP.magic;

  at24Write(
    0,
    (uint8_t*)&gripCalibration,
    sizeof(gripCalibration)
  );
}

void loadPersistentData() {
  EEPROM.get(EEPROM_GIMBAL, gimbalCalibration);

  if (gimbalCalibration.magic != DEFAULT_GIMBAL.magic) {
    gimbalCalibration = DEFAULT_GIMBAL;
    EEPROM.put(EEPROM_GIMBAL, gimbalCalibration);
  }

  EEPROM.get(EEPROM_SETTINGS, settings);

  if (settings.magic != DEFAULT_SETTINGS.magic) {
    settings = DEFAULT_SETTINGS;
    EEPROM.put(EEPROM_SETTINGS, settings);
  }

  gripCalibration = DEFAULT_GRIP;

  if (at24Present) {
    GripCalibration temporary;

    if (
      at24Read(
        0,
        (uint8_t*)&temporary,
        sizeof(temporary)
      ) &&
      temporary.magic == DEFAULT_GRIP.magic
    ) {
      gripCalibration = temporary;
    } else {
      saveGripCalibration();
    }
  }
}

void saveSettings() {
  settings.magic = DEFAULT_SETTINGS.magic;
  EEPROM.put(EEPROM_SETTINGS, settings);
}

void saveGimbalCalibration() {
  gimbalCalibration.magic = DEFAULT_GIMBAL.magic;
  EEPROM.put(EEPROM_GIMBAL, gimbalCalibration);
}

int axisIndexByName(String name) {
  name.trim();
  name.toUpperCase();

  for (int i = 0; i < AXIS_COUNT; i++) {
    if (name == AXIS_NAMES[i]) return i;
  }

  return -1;
}

void printIdentity() {
  Serial.print("ID|HFB|STICK|");
  Serial.print(FW_VERSION);
  Serial.print("|");
  Serial.println(HOTAS_PROTOCOL_VERSION);
}

void printSettings() {
  Serial.print("CFG|STICK|INV=");

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
  Serial.print(settings.atb[0]);
  Serial.print(",");
  Serial.print(settings.atb[1]);

  Serial.print("|DZ=");

  for (int i = 0; i < AXIS_COUNT; i++) {
    if (i) Serial.print(",");
    Serial.print(settings.deadzone[i]);
  }

  Serial.println();
}

void readHardware() {
  rawValues[AX_X] = adsGimbal.readADC(0);
  rawValues[AX_Y] = adsGimbal.readADC(1);

  rawValues[AX_Z] = adsGrip.readADC(0);
  rawValues[AX_RX] = adsGrip.readADC(1);
  rawValues[AX_RY] = adsGrip.readADC(2);
  rawValues[AX_RZ] = adsGrip.readADC(3);
}

long calibrationMinimum(int index) {
  if (index == AX_X) return gimbalCalibration.xMin;
  if (index == AX_Y) return gimbalCalibration.yMin;

  return gripCalibration.minimum[index - 2];
}

long calibrationMaximum(int index) {
  if (index == AX_X) return gimbalCalibration.xMax;
  if (index == AX_Y) return gimbalCalibration.yMax;

  return gripCalibration.maximum[index - 2];
}

void storeCalibrationRange(
  int index,
  long minimum,
  long maximum
) {
  minimum = constrain(minimum, 0L, 65535L);
  maximum = constrain(maximum, 0L, 65535L);

  if (index == AX_X) {
    gimbalCalibration.xMin = minimum;
    gimbalCalibration.xMax = maximum;
  } else if (index == AX_Y) {
    gimbalCalibration.yMin = minimum;
    gimbalCalibration.yMax = maximum;
  } else {
    gripCalibration.minimum[index - 2] = minimum;
    gripCalibration.maximum[index - 2] = maximum;
  }
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

  const uint8_t secondPins[11] = {
    0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 12
  };

  for (int i = 0; i < 11; i++) {
    bool pressed =
      !((second >> secondPins[i]) & 1);

    int index = i + 16;

    Joystick.setButton(index, pressed);

    if (pressed) buttonMask |= (1UL << index);
  }
}

void processAxes() {
  for (int i = 0; i < AXIS_COUNT; i++) {
    applyAdaptiveEMA(
      rawValues[i],
      filtered[i],
      i < 2 ? settings.filters[0] : settings.filters[1],
      3
    );

    int value = applyAxisProcessing(
      filtered[i],
      calibrationMinimum(i),
      calibrationMaximum(i),
      settings.deadzone[i],
      settings.inverted[i]
    );

    output[i] = applyHysteresis(
      value,
      lastOutput[i],
      settings.jitter
    );
  }

  Joystick.setXAxis(output[AX_X]);
  Joystick.setYAxis(output[AX_Y]);
  Joystick.setZAxis(output[AX_Z]);

  if (settings.atb[0]) {
    bool up = output[AX_RY] > 8000;
    bool down = output[AX_RY] < -8000;
    bool right = output[AX_RX] > 8000;
    bool left = output[AX_RX] < -8000;

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
    Joystick.setRxAxis(0);
    Joystick.setRyAxis(0);
  } else {
    hatValue = -1;
    Joystick.setHatSwitch(0, -1);
    Joystick.setRxAxis(output[AX_RX]);
    Joystick.setRyAxis(output[AX_RY]);
  }

  if (settings.atb[1]) {
    bool brakePressed = output[AX_RZ] > 8000;

    Joystick.setButton(27, brakePressed);
    Joystick.setRzAxis(0);

    if (brakePressed) buttonMask |= (1UL << 27);
    else buttonMask &= ~(1UL << 27);
  } else {
    Joystick.setButton(27, false);
    Joystick.setRzAxis(output[AX_RZ]);
    buttonMask &= ~(1UL << 27);
  }

  digitalWrite(
    LED_ATB_PIN,
    settings.atb[0] || settings.atb[1]
  );
}

void sendTelemetry() {
  if (!streamEnabled) return;

  unsigned long interval = 1000UL / max(1, streamRate);

  if (millis() - lastStream < interval) return;
  lastStream = millis();

  Serial.print("DATA|STICK");

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

  Serial.print("CAL|STICK|BEGIN|");
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

    Serial.print("CAL|STICK|VALUE|");
    Serial.print(AXIS_NAMES[calibrationAxis]);
    Serial.print("|");
    Serial.print(calibrationMin);
    Serial.print("|");
    Serial.println(calibrationMax);
  }
}

void nextCalibrationAxis() {
  if (!calibrationActive) return;

  if (calibrationMax - calibrationMin < 50) {
    Serial.println("ERR|CALIBRATION_RANGE_TOO_SMALL");
    return;
  }

  storeCalibrationRange(
    calibrationAxis,
    calibrationMin,
    calibrationMax
  );

  calibrationAxis++;

  if (calibrationAxis >= AXIS_COUNT) {
    calibrationActive = false;

    saveGimbalCalibration();
    saveGripCalibration();

    Serial.println("CAL|STICK|DONE");
  } else {
    beginCalibrationAxis();
  }
}

void processSetCommand(String command) {
  if (command.startsWith("SET INV ")) {
    String content = command.substring(8);
    int separator = content.lastIndexOf(' ');

    int index = axisIndexByName(
      content.substring(0, separator)
    );

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

    if (number < 1 || number > 2) {
      Serial.println("ERR|UNKNOWN_ATB");
      return;
    }

    settings.atb[number - 1] =
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

    if (!at24Present) {
      Serial.println("WARN|AT24C32_NOT_FOUND");
    }
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
    Serial.println("CAL|STICK|CANCELLED");
  }
  else if (command.startsWith("SET ")) processSetCommand(command);
  else Serial.println("ERR|UNKNOWN_COMMAND");
}

void setup() {
  Serial.begin(SERIAL_BAUD);

  Wire.begin();
  Wire.setClock(400000);

  Wire.beginTransmission(AT24_ADDRESS);
  at24Present = Wire.endTransmission() == 0;

  adsGrip.begin();
  adsGimbal.begin();

  adsGrip.setDataRate(7);
  adsGimbal.setDataRate(7);

  pcf1.begin();
  pcf2.begin();

  pcf1.setButtonMask(0xFFFF);
  pcf2.setButtonMask(0xFFFF);

  pinMode(LED_ATB_PIN, OUTPUT);

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
