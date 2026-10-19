#ifndef HOTAS_COMMON_H
#define HOTAS_COMMON_H

#include <Arduino.h>

#define HOTAS_PROTOCOL_VERSION 2
#define HOTAS_AXIS_MIN -16384
#define HOTAS_AXIS_MAX 16384

inline float clampAlpha(float value) {
  if (value < 0.01f) return 0.01f;
  if (value > 1.0f) return 1.0f;
  return value;
}

inline uint16_t clampDeadzone(long value) {
  if (value < 0) return 0;
  if (value > 8000) return 8000;
  return (uint16_t)value;
}

inline uint16_t clampJitter(long value) {
  if (value < 0) return 0;
  if (value > 2000) return 2000;
  return (uint16_t)value;
}

inline int mapAxisSafe(
  long value,
  long inputMin,
  long inputMax
) {
  if (inputMax <= inputMin) return 0;

  value = constrain(value, inputMin, inputMax);

  return (int)map(
    value,
    inputMin,
    inputMax,
    HOTAS_AXIS_MIN,
    HOTAS_AXIS_MAX
  );
}

inline int applyCenterDeadzone(
  int value,
  uint16_t deadzone
) {
  if (deadzone == 0) return value;
  if (deadzone >= HOTAS_AXIS_MAX) return 0;

  long magnitude = abs((long)value);

  if (magnitude <= deadzone) return 0;

  long scaled = map(
    magnitude,
    deadzone,
    HOTAS_AXIS_MAX,
    0,
    HOTAS_AXIS_MAX
  );

  scaled = constrain(
    scaled,
    0L,
    (long)HOTAS_AXIS_MAX
  );

  return value < 0 ? -(int)scaled : (int)scaled;
}

inline int applyAxisProcessing(
  long filteredValue,
  long inputMin,
  long inputMax,
  uint16_t deadzone,
  bool inverted
) {
  int result = mapAxisSafe(
    filteredValue,
    inputMin,
    inputMax
  );

  result = applyCenterDeadzone(
    result,
    deadzone
  );

  if (inverted) result = -result;

  return constrain(
    result,
    HOTAS_AXIS_MIN,
    HOTAS_AXIS_MAX
  );
}

inline int applyHysteresis(
  int current,
  int &last,
  uint16_t threshold
) {
  if (abs(current - last) >= threshold) {
    last = current;
  }

  return last;
}

inline void applyAdaptiveEMA(
  long rawValue,
  float &filteredValue,
  float baseAlpha,
  uint8_t shiftBits
) {
  baseAlpha = clampAlpha(baseAlpha);

  long truncated = (
    rawValue >> shiftBits
  ) << shiftBits;

  float difference = abs(
    (float)truncated - filteredValue
  );

  float dynamicAlpha = baseAlpha;

  float lowThreshold = max(
    1.0f,
    32.0f / (1 << shiftBits)
  );

  float highThreshold = max(
    2.0f,
    256.0f / (1 << shiftBits)
  );

  if (difference < lowThreshold) {
    dynamicAlpha = baseAlpha * 0.1f;
  } else if (difference > highThreshold) {
    dynamicAlpha = 0.85f;
  }

  filteredValue =
    dynamicAlpha * truncated +
    (1.0f - dynamicAlpha) * filteredValue;
}

inline bool parseLastInt(
  const String &command,
  String &prefix,
  long &value
) {
  int position = command.lastIndexOf(' ');

  if (position < 0) return false;

  prefix = command.substring(0, position);
  String valueText = command.substring(position + 1);

  valueText.trim();

  if (valueText.length() == 0) return false;

  value = valueText.toInt();
  return true;
}

#endif
