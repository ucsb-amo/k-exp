#include "qCommand.h"

qCommand qC;

struct Cal {
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16];
};

volatile float set1 = 3.0f, kp1 = 0.10f, ki1 = 0.30f, g1 = 0.5f, dV = 5.0f, m = 1.0f;
volatile float tor = 0.5f, st_thresh = 0.9f;
volatile bool pid_enable1 = true, manual_override1 = false;
volatile bool enable_print = true;
volatile float y_print, u_print, sp_print, contrast_print = 0.0f, max_print = 0.0f, min_print = 0.0f;

static constexpr float DT_SEC = 1.0e-4f; 
static constexpr float OUT_MIN = 0.0f, OUT_MAX = 10.0f;

volatile float u_last_hold = 0.0f, integ1 = 0.0f;

void phaseLock();
void pid1();
void triangleSweep();
void ping(qCommand& qC, Stream& S);
void toggleManual(qCommand& qC, Stream& S);

void togglePrint(qCommand& qC, Stream& S) { 
    enable_print = !enable_print; 
}

static inline float clampf(float x, float lo, float hi) {
    return (x < lo) ? lo : (x > hi) ? hi : x;
}

void setup() {
    Serial.begin(115200);
    configureADC(1, 1, 0, BIPOLAR_10V, phaseLock);

    qC.assignVariable("set1", (float*)&set1);
    qC.assignVariable("p1",   (float*)&kp1);
    qC.assignVariable("i1",   (float*)&ki1);
    qC.assignVariable("g1",   (float*)&g1);
    qC.assignVariable("mode", (float*)&m);
    
    qC.addCommand("m", toggleManual);
    qC.addCommand("s", togglePrint); 
    qC.addCommand("ping", ping);
}

void loop() {
    qC.readSerial(Serial);
    static uint32_t last_ms = 0;    
    if (enable_print && (millis() - last_ms >= 100)) { 
        last_ms = millis();
        if (m == 1.0f) {
            Serial.print("sp:"); Serial.print(sp_print, 2);
            Serial.print(" in:"); Serial.print(y_print, 3);
            Serial.print(" out:"); Serial.println(u_print, 3);
        } else if (m == 2.0f) {
            Serial.print("out:"); Serial.print(u_print, 2);
            Serial.print(" max:"); Serial.print(max_print, 2);
            Serial.print(" min:"); Serial.print(min_print, 2);
            Serial.print(" contrast:"); Serial.println(contrast_print, 4);
        }
    }
}


void ping(qCommand& qC, Stream& S) {
    struct Cal cal2;
    readNVMblock(&cal2, sizeof(cal2), 0xFA00);  
    Serial.println(cal2.cal_d); 
}

void toggleManual(qCommand& qC, Stream& S) { 
    manual_override1 = !manual_override1; 
}

void phaseLock() {
    if (m == 1.0f) {
        pid1();
    } 
    else if (m == 2.0f) {
        triangleSweep();
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

    y_print = y; 
    u_print = u_last_hold; 
    sp_print = set1;
}

void triangleSweep() {
    static float v = 0.0f;
    static float dir = 1.0f;
    static float step = 0.01f; 
    static float cur_max = -10.0f;
    static float cur_min = 10.0f;

    v += dir * 0.05f * step;
    const float y = (float)readADC1_from_ISR();

    if (y > cur_max) cur_max = y;
    if (y < cur_min) cur_min = y;

    if (v >= 10.0f) {
        v = 10.0f;
        dir = -1.0f;
    } 
    else if (v <= 0.0f) {
        v = 0.0f;
        dir = 1.0f;
        
        if (cur_max + cur_min != 0) {
            contrast_print = (cur_max - cur_min) / (cur_max + cur_min);
        }
        cur_max = -10.0f;
        cur_min = 10.0f;
    }
    
    writeDAC(1, v);
    
    u_print = v;
    y_print = y;
    max_print = cur_max;
    min_print = cur_min;
}