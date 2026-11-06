// raman_intensity_control: intensity stabilization of the two Raman beams on one Quarto.
// Based on ../pid_intensity_stabilize_ry_3418 (same wiring idea, same sign convention).
//
// Wiring
//   loop 1: photodiode IN1, setpoint (analog, from ARTIQ) IN2 -> control OUT1 (VVA 1), error monitor OUT3
//   loop 2: photodiode IN3, setpoint (analog, from ARTIQ) IN4 -> control OUT2 (VVA 2), error monitor OUT4
//
// Control law, on every photodiode sample (every 1 us):
//   err   = PD - setpoint                                  [V]
//   integ = integ + i*err   (skipped when the output is already at a limit and err would push it further)
//   out   = p*err + integ, clamped to [omin, omax]         [V] -> VVA control input
// p and i are negative: too much light (err > 0) lowers the VVA voltage, which lowers the RF power.
// i acts once per sample, so at 1 MHz i = -0.006 ramps the output by 6 V/s per mV of error.
// Changing the ADC period below changes the effective integral gain.
//
// Serial commands (send a name alone to read it, "name value" to set it). Loop 2: same names ending in 2.
//   p1 i1        proportional and per-sample integral gain (V/V)
//   omin1 omax1  V, output limits sent to the VVA (also clamp the integrator). Kept inside +/-10 V.
//                If omin1 > omax1 the output is pinned at omax1.
//   lock1        1 = the PI loop drives the output; 0 = output fixed at vman1 (use to map VVA voltage
//                -> optical power when calibrating omin/omax). Going 0 -> 1 starts the integrator at
//                the current output, so the output only steps by the proportional term p1*err1.
//   vman1        V, the output while lock1 = 0 (still clamped to [omin1, omax1])
//   read only:   pd1 set1 err1 out1 integ1 (V), rail1 (1 = output at a limit, lock on),
//                nrail1 (times the output went to a limit since power-up)
//   s            status table of both loops
//   c / clear    zero both integrators
//   help         this list with current values
//   ping         prints the board label stored in NVM (written by name_quarto.ino)
//
// Serial changes live in RAM only and are lost at power-off. After calibrating, put the values below as
// the new defaults: comment out the old line, tag the new one with the run id and date.
#include "qCommand.h"
qCommand qC;

struct Cal
{
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16];
};

// V, hard cap on every output. The Quarto DAC itself spans +/-10.24 V (16 bit, 0.3125 mV/step) and
// writeDAC clamps out-of-range values to full scale, it does not wrap (qNimble core 2.5.3, dac.cpp).
const double DAC_MAX = 10.0;

struct Loop {
  // settings (serial)
  double p = -0.055;    // V/V
  double i = -0.006;    // V/V per sample
  double omin = 0.0;    // V, lowest voltage sent to the VVA
  double omax = 10.0;   // V, highest voltage sent to the VVA (VVA control range 0-10 V); calibrate
  int32_t lock = 1;     // 1 = PI loop on; 0 = output fixed at vman
  double vman = 0.0;    // V, output while lock = 0
  // read only
  double pd = 0;        // V, photodiode
  double setp = 0;      // V, setpoint input
  double err = 0;       // V, pd - setp
  double out = 0;       // V, sent to the VVA
  double integ = 0;     // V, integrator
  int32_t rail = 0;     // 1 = output at omin or omax while locking
  uint32_t nrail = 0;   // times the output went to a limit
};

Loop L1, L2;

static inline double clampd(double x, double lo, double hi) {
  if (x > hi) return hi;
  if (x < lo) return lo;
  return x;
}

// One PI update. Called from the photodiode ISR of its loop.
void step(Loop& L, double pd, uint8_t outCh, uint8_t monCh) {
  L.pd = pd;
  L.err = pd - L.setp;

  double hi = clampd(L.omax, -DAC_MAX, DAC_MAX);
  double lo = clampd(L.omin, -DAC_MAX, DAC_MAX);
  if (lo > hi) lo = hi;  // misordered limits: pin at omax

  double out;
  if (L.lock == 1) {
    double di = L.i * L.err;
    double u = L.p * L.err + L.integ + di;
    // anti-windup: do not integrate further into a limit
    bool into_hi = (u > hi) && (di > 0);
    bool into_lo = (u < lo) && (di < 0);
    if (!into_hi && !into_lo) L.integ += di;
    L.integ = clampd(L.integ, lo, hi);
    out = clampd(L.p * L.err + L.integ, lo, hi);

    int32_t railNow = (out >= hi || out <= lo) ? 1 : 0;
    if (railNow && !L.rail) L.nrail++;
    L.rail = railNow;
  } else {
    out = clampd(L.vman, lo, hi);
    L.integ = out;  // lock 1 then restarts from this output (plus the p*err step)
    L.rail = 0;
  }

  L.out = out;
  writeDAC(outCh, out);
  writeDAC(monCh, clampd(L.err, -DAC_MAX, DAC_MAX));
}

// ---- ADC interrupt routines ----
void getMeas1() { step(L1, readADC1_from_ISR(), 1, 3); }
void getSet1()  { L1.setp = readADC2_from_ISR(); }
void getMeas2() { step(L2, readADC3_from_ISR(), 2, 4); }
void getSet2()  { L2.setp = readADC4_from_ISR(); }

// ---- serial commands ----
void ping(qCommand& qC, Stream& S)
{
  struct Cal cal2;
  readNVMblock(&cal2, sizeof(cal2), 0xFA00);
  S.println(cal2.cal_d);
}

void clearIntegrators(qCommand& qC, Stream& S)
{
  noInterrupts();
  L1.integ = 0;
  L2.integ = 0;
  interrupts();
  S.println("integrators cleared (both loops)");
}

void printLoop(Stream& S, const char* name, const Loop& L)
{
  S.printf("%-5s %+8.4f %+8.4f %+9.5f %+8.4f %+8.4f %4ld %-4s %7lu\n",
           name, L.pd, L.setp, L.err, L.out, L.integ, (long)L.lock,
           L.rail ? "RAIL" : "-", (unsigned long)L.nrail);
}

void status(qCommand& qC, Stream& S)
{
  noInterrupts();
  Loop a = L1;
  Loop b = L2;
  interrupts();
  S.println("loop    pd V   set V     err V    out V  integ V lock rail   nrail");
  printLoop(S, "1", a);
  printLoop(S, "2", b);
}

void helpLoop(Stream& S, int n, const Loop& L)
{
  S.printf("loop %d:\n", n);
  S.printf("  p%d     %+10.5g V/V         proportional\n", n, L.p);
  S.printf("  i%d     %+10.5g V/V/sample  integral, per 1 us sample\n", n, L.i);
  S.printf("  omin%d  %+10.4f V           lowest output to the VVA\n", n, L.omin);
  S.printf("  omax%d  %+10.4f V           highest output to the VVA\n", n, L.omax);
  S.printf("  lock%d  %10ld             1 = PI on; 0 = output fixed at vman%d\n", n, (long)L.lock, n);
  S.printf("  vman%d  %+10.4f V           output while lock%d = 0\n", n, L.vman, n);
}

void help(qCommand& qC, Stream& S)
{
  noInterrupts();
  Loop a = L1;
  Loop b = L2;
  interrupts();
  S.println("Raman intensity lock, 2 loops. Send a name to read it, 'name value' to set it.");
  S.println("IN1 PD1, IN2 set1 -> OUT1 VVA1, OUT3 err1 | IN3 PD2, IN4 set2 -> OUT2 VVA2, OUT4 err2");
  S.println("out = clamp(p*err + integ, omin, omax), err = PD - setpoint");
  helpLoop(S, 1, a);
  helpLoop(S, 2, b);
  S.println("read only: pd set err out integ rail nrail (append 1 or 2)");
  S.println("s (status), c / clear (zero integrators), ping (board label), help");
}

void setup() {
  Serial.begin(115200);

  // outputs to a known state before the loops start
  writeDAC(1, L1.omin);
  writeDAC(2, L2.omin);
  writeDAC(3, 0.0);
  writeDAC(4, 0.0);

  qC.addCommand("ping", ping);
  qC.addCommand("help", help);
  qC.addCommand("s", status);
  qC.addCommand("c", clearIntegrators);
  qC.addCommand("clear", clearIntegrators);

  qC.assignVariable("p1", &L1.p);
  qC.assignVariable("i1", &L1.i);
  qC.assignVariable("omin1", &L1.omin);
  qC.assignVariable("omax1", &L1.omax);
  qC.assignVariable("lock1", &L1.lock);
  qC.assignVariable("vman1", &L1.vman);
  qC.assignVariable("pd1", &L1.pd, true);
  qC.assignVariable("set1", &L1.setp, true);
  qC.assignVariable("err1", &L1.err, true);
  qC.assignVariable("out1", &L1.out, true);
  qC.assignVariable("integ1", &L1.integ, true);
  qC.assignVariable("rail1", &L1.rail, true);
  qC.assignVariable("nrail1", &L1.nrail, true);

  qC.assignVariable("p2", &L2.p);
  qC.assignVariable("i2", &L2.i);
  qC.assignVariable("omin2", &L2.omin);
  qC.assignVariable("omax2", &L2.omax);
  qC.assignVariable("lock2", &L2.lock);
  qC.assignVariable("vman2", &L2.vman);
  qC.assignVariable("pd2", &L2.pd, true);
  qC.assignVariable("set2", &L2.setp, true);
  qC.assignVariable("err2", &L2.err, true);
  qC.assignVariable("out2", &L2.out, true);
  qC.assignVariable("integ2", &L2.integ, true);
  qC.assignVariable("rail2", &L2.rail, true);
  qC.assignVariable("nrail2", &L2.nrail, true);

  // 1 us sample period, ADCs in phase, +/-10 V input range
  configureADC(1, 1, 0, BIPOLAR_10V, getMeas1);
  configureADC(2, 1, 0, BIPOLAR_10V, getSet1);
  configureADC(3, 1, 0, BIPOLAR_10V, getMeas2);
  configureADC(4, 1, 0, BIPOLAR_10V, getSet2);
}

void loop() {
  qC.readSerial(Serial);
}
