#include "qCommand.h"
qCommand qC;

struct Cal 
{
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16];
};

volatile float set1 = 1.5f, kp1 = 0.10f, ki1 = 0.30f, g1 = 0.5f, dV = 5.0f;
// volatile float set1 = 3.0f, kp1 = 0.10f, ki1 = 0.10f, g1 = 0.5f, dV = 5.0f;
volatile float tor = 0.5f;      
volatile float st_thresh = 0.9f; 
volatile bool pid_enable1 = true, manual_override1 = false;

volatile float u_last_hold = 0.0f, integ1 = 0.0f, y_prev = 0.0f, dy_filt = 0.0f;
volatile float y_print, u_print, sp_print;
volatile long c_print = 0;
volatile long n_print = 0;

static constexpr float DT_SEC = 1.0e-4f; 
static constexpr float OUT_MIN = 0.0f, OUT_MAX = 10.0f;
static constexpr float D_ALPHA = 0.1f, ERR_DB = 0.003f;

static inline float clampf(float x, float lo, float hi) {
  return (x < lo) ? lo : (x > hi) ? hi : x;
}

void pid1();
void toggleManual(qCommand& qC, Stream& S) { manual_override1 = !manual_override1; }

void setup() {
  Serial.begin(115200);
  configureADC(1, 1, 0, BIPOLAR_10V, pid1);

  qC.assignVariable("set1", (float*)&set1);
  qC.assignVariable("p1",   (float*)&kp1);
  qC.assignVariable("i1",   (float*)&ki1);
  qC.assignVariable("g1",   (float*)&g1);
  qC.addCommand("m", toggleManual);
  qC.addCommand("ping",ping);
}

void ping(qCommand& qC, Stream& S)
{
  struct Cal cal2;
  readNVMblock(&cal2, sizeof(cal2), 0xFA00);  
  Serial.println(cal2.cal_d); 
}

void loop() {
  qC.readSerial(Serial);
  static uint32_t last_ms = 0;
  if (millis() - last_ms >= 100) { 
    last_ms = millis();
    Serial.print("sp:"); Serial.print(sp_print, 2);
    Serial.print(" in:"); Serial.print(y_print, 3);
    Serial.print(" out:"); Serial.println(u_print, 3);
    // Serial.print(" c:");  Serial.print(c_print);
    // Serial.print(" N:");  Serial.print(n_print);
    
  }
}

void pid1() {
  static bool last_trig = false;
  static float c = 0, N = 0;
  
  const bool current_trig = triggerRead(1);
  const bool rising_edge = (current_trig && !last_trig);
  last_trig = current_trig;

  const float y = (float)readADC1_from_ISR();
  
  if (rising_edge) {
    // u_last_hold = 5.0f;
    // integ1 = 10.0f; 
    // y_prev = y;
    // dy_filt = 0.0f;
    c = 0; N = 0;
    writeDAC(2, 0.0f);
  }


  if (manual_override1 || !pid_enable1) {
    writeDAC(1, u_last_hold); 
    writeDAC(2, 0.0f);
    return;
  }

  float raw_err = set1 - y;
  float pid_err = (raw_err < ERR_DB && raw_err > -ERR_DB) ? 0.0f : raw_err;

  y_prev = y;
  
  integ1 += pid_err * ki1 * DT_SEC;
  float u_total = g1 * ((kp1 * pid_err) + integ1);

  if (u_total > 9.9f) { integ1 -= (dV / g1); u_total -= dV; } 
  else if (u_total < 0.1f) { integ1 += (dV / g1); u_total += dV; }

  u_last_hold = clampf(u_total, OUT_MIN, OUT_MAX);
  writeDAC(1, u_last_hold);

    N = N + 1;
    if (raw_err < 1.5*tor && raw_err > -1.5*tor) {
      if (raw_err > tor && raw_err < -tor) {
          c = c *0.5; 
      }
      else{ c = c + 1;} 
    }
    else {
      c = 0;
      writeDAC(2, 0.0f);
    }
    if (N > 500 && (float)c >= ((float)N * st_thresh)) {
      writeDAC(2, 5.0f);
    } else {
      writeDAC(2, 0.0f);
    }

  y_print = y;
  u_print = u_last_hold;
  sp_print = set1;
  c_print = c;
  n_print = N;
}