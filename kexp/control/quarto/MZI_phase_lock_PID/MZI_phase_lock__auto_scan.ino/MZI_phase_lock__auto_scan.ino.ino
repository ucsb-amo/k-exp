#include "qCommand.h"
#include <math.h>

qCommand qC;

struct Cal {
  uint16_t cal_a;
  double   cal_b;
  uint16_t cal_c;
  char     cal_d[16];
};

// ===================== User variables =====================
volatile float set1 = .15f, kp1 = 0.05f, ki1 = 10.0f, g1 = 0.5f, dV = 5.0f, m = 1.0f;
volatile float tor = 0.5f, st_thresh = 0.9f;
volatile bool  pid_enable1 = true, manual_override1 = false;
volatile bool  enable_print = true;

volatile float y_print = 0.0f, y2_print = 0.0f, u_print = 0.0f, sp_print = 0.0f;
volatile float contrast_print = 0.0f, max_print = 0.0f, min_print = 0.0f;

// one-shot scan status/results
volatile bool  scan_active = false;
volatile bool  scan_done   = false;
volatile float y2max_print = 0.0f;
volatile float y_at_y2max_print = 0.0f;
volatile float v_at_y2max_print = 0.0f;

static constexpr float DT_SEC  = 1.0e-4f;
static constexpr float OUT_MIN = 0.0f, OUT_MAX = 10.0f;

volatile float u_last_hold = 0.0f, integ1 = 0.0f;

// ===================== Forward decls =====================
void phaseLock();        // ADC1 ISR callback (ONLY control loop)
void adc2Capture();      // ADC2 ISR callback (capture only)

void pid1();
void triangleSweep();
void autoScan_oneShot(); // overlay scan

void ping(qCommand& qC, Stream& S);
void toggleManual(qCommand& qC, Stream& S);
void togglePrint(qCommand& qC, Stream& S);
void startScan(qCommand& qC, Stream& S);

static inline float clampf(float x, float lo, float hi) {
  return (x < lo) ? lo : (x > hi) ? hi : x;
}

// ===================== Commands =====================
void togglePrint(qCommand& qC, Stream& S) { enable_print = !enable_print; }
void toggleManual(qCommand& qC, Stream& S) { manual_override1 = !manual_override1; }

void startScan(qCommand& qC, Stream& S) {
  const int mode = (int)lroundf(m);
  if (mode != 1 && mode != 2) {
    Serial.println("scan ignored (mode must be 1 or 2)");
    return;
  }
  scan_active = true;
  scan_done   = false;
  Serial.println("scan started (0 -> 5 one-shot)");
}

void ping(qCommand& qC, Stream& S) {
  Cal cal2;
  readNVMblock(&cal2, sizeof(cal2), 0xFA00);
  Serial.println(cal2.cal_d);
}

// ===================== Setup / Loop =====================
void setup() {
  Serial.begin(115200);

  // ADC1 runs the control loop
  configureADC(1, 1, 0, BIPOLAR_10V, phaseLock);

  // ADC2 ONLY captures y2_print and clears its interrupt
  configureADC(2, 1, 1, BIPOLAR_10V, adc2Capture);

  qC.assignVariable("set1", (float*)&set1);
  qC.assignVariable("p1",   (float*)&kp1);
  qC.assignVariable("i1",   (float*)&ki1);
  qC.assignVariable("g1",   (float*)&g1);
  qC.assignVariable("mode", (float*)&m);

  qC.addCommand("m", toggleManual);
  qC.addCommand("s", togglePrint);
  qC.addCommand("ping", ping);
  qC.addCommand("scan", startScan);
}

void loop() {
  qC.readSerial(Serial);

  static uint32_t last_ms = 0;
  if (!enable_print || (millis() - last_ms < 100)) return;
  last_ms = millis();

  const int mode = (int)lroundf(m);

  if (mode == 1) {
    Serial.print("mode 1 ");
    Serial.print("sp:");  Serial.print(sp_print, 4);
    Serial.print(" in:"); Serial.print(y_print, 3);
    Serial.print(" out:");Serial.print(u_print, 3);
  } else if (mode == 2) {
    Serial.print("mode 2 ");
    Serial.print("out:"); Serial.print(u_print, 2);
    Serial.print(" max:");Serial.print(max_print, 2);
    Serial.print(" min:");Serial.print(min_print, 2);
    Serial.print(" contrast:"); Serial.print(contrast_print, 4);
  } else {
    Serial.print("mode? ");
  }

  // always show APD readout (since ADC2 is always sampling)
  Serial.print(" APD:"); Serial.print(y2_print, 3);

  if (scan_done) {
    scan_done = false; // print once
    Serial.print(" | y2max:"); Serial.print(y2max_print, 3);
    Serial.print(" y@max:");  Serial.print(y_at_y2max_print, 3);
    Serial.print(" v@max:");  Serial.print(v_at_y2max_print, 3);
  }
  Serial.println();
}

// ===================== ISR callbacks =====================

// ADC2 callback: MUST call readADC2_from_ISR() to clear interrupt
void adc2Capture() {
  y2_print = (float)readADC2_from_ISR();
}

// ADC1 callback: MUST always clear ADC1 interrupt by calling readADC1_from_ISR()
// We do that inside pid1/triangle/scan; if mode is unknown we still clear it.
void phaseLock() {
  const int mode = (int)lroundf(m);

  // --- overlay scan takes priority in BOTH mode 1 and mode 2 ---
  if (scan_active) {
    autoScan_oneShot();   // reads ADC1 and clears interrupt
    return;
  }

  if (mode == 1) {
    pid1();               // reads ADC1 and clears interrupt
  } else if (mode == 2) {
    triangleSweep();      // reads ADC1 and clears interrupt
  } else {
    // fail-safe: clear interrupt even in unknown mode
    y_print = (float)readADC1_from_ISR();
  }
}

// ===================== Mode 1: PID =====================
void pid1() {
  static bool  last_trig = false;
  static float c = 0, N = 0;

  const bool current_trig = triggerRead(1);
  const bool rising_edge = (current_trig && !last_trig);
  last_trig = current_trig;

  const float y = (float)readADC1_from_ISR(); // clears ADC1 interrupt

  if (rising_edge) {
    c = 0; N = 0;
    writeDAC(2, 0.0f);
  }

  if (manual_override1 || !pid_enable1) {
    writeDAC(1, u_last_hold);
    return;
  }

  float raw_err = set1 - y;
  float pid_err = (raw_err < 0.003f && raw_err > -0.003f) ? 0.0f : raw_err;

  integ1 += pid_err * ki1 * DT_SEC;
  float u_total = g1 * ((kp1 * pid_err) + integ1);

  if (u_total > 9.9f) { integ1 -= (dV / g1); u_total -= dV; }
  else if (u_total < 0.1f) { integ1 += (dV / g1); u_total += dV; }

  u_last_hold = clampf(u_total, OUT_MIN, OUT_MAX);
  writeDAC(1, u_last_hold);

  N += 1.0f;
  if (raw_err < 1.5f * tor && raw_err > -1.5f * tor) {
    if (raw_err > tor || raw_err < -tor) c *= 0.5f;
    else c += 1.0f;
  } else {
    c = 0;
    writeDAC(2, 0.0f);
  }
  if (N > 500 && c >= (N * st_thresh)) writeDAC(2, 5.0f);
  else writeDAC(2, 0.0f);

  y_print  = y;
  u_print  = u_last_hold;
  sp_print = set1;
}

// ===================== Mode 2: Triangle sweep (continuous) =====================
void triangleSweep() {
  static float v = 0.0f;
  static float dir = 1.0f;
  static float step = 0.01f;
  static float cur_max = -10.0f;
  static float cur_min =  10.0f;

  v += dir * 0.01f * step;
  const float y = (float)readADC1_from_ISR(); // clears ADC1 interrupt

  if (y > cur_max) cur_max = y;
  if (y < cur_min) cur_min = y;

  if (v >= 5.0f) { v = 5.0f; dir = -1.0f; }
  else if (v <= 0.0f) {
    v = 0.0f; dir = 1.0f;
    if (cur_max + cur_min != 0.0f) contrast_print = (cur_max - cur_min) / (cur_max + cur_min);
    cur_max = -10.0f; cur_min = 10.0f;
  }

  writeDAC(1, v);

  u_print = v;
  y_print = y;
  max_print = cur_max;
  min_print = cur_min;
}

// ===================== Overlay: One-shot scan (0 -> 5 once) =====================
void autoScan_oneShot() {
  static float v = 0.0f;
  static float step = 0.01f;

  static float cur_max = -10.0f;
  static float cur_min =  10.0f;

  static float y2_max = -1.0e30f;
  static float y_at_max = 0.0f;
  static float v_at_max = 0.0f;

  static bool was_active = false;

  // detect start edge to reset scan state
  if (scan_active && !was_active) {
    v = 0.0f;
    cur_max = -10.0f;
    cur_min =  10.0f;
    y2_max  = -1.0e30f;
    y_at_max = 0.0f;
    v_at_max = 0.0f;
    writeDAC(1, v);
  }
  was_active = scan_active;

  const float y  = (float)readADC1_from_ISR(); // clears ADC1 interrupt
  const float y2 = y2_print;                   // captured by ADC2 ISR

  if (y > cur_max) cur_max = y;
  if (y < cur_min) cur_min = y;

  if (y2 > y2_max) {
    y2_max  = y2;
    y_at_max = y;
    v_at_max = v;
  }

  // advance upward only
  v += 0.01f * step;
  if (v > 5.0f) v = 5.0f;

  writeDAC(1, v);

  u_print = v;
  y_print = y;
  max_print = cur_max;
  min_print = cur_min;

  if (v >= 5.0f) {
    if (cur_max + cur_min != 0.0f) {
      contrast_print = (cur_max - cur_min) / (cur_max + cur_min);
    }

    y2max_print = y2_max;
    y_at_y2max_print = y_at_max;
    v_at_y2max_print = v_at_max;
    set1 = y_at_max;
    scan_active = false;
    scan_done   = true;
  }
}
