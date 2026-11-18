// Raman laser frequency lock on the scanning Fabry-Perot cavity (Quarto).
//
// The cavity length is swept by a sawtooth; trigger 1 goes high at the start of
// each sweep. The cavity transmission (ADC 1) shows one peak per laser. Each
// sweep, the lock measures the time between the first two peaks after the
// trigger edge (sep, in ms) and feeds back on DAC 1 so that sep = setp:
//
//   err    = sep - setp
//   integ  = integ + g1*i1*err          (once per sweep)
//   output = g1*p1*err + integ          (output and integ clamped to +/-RAIL)
//
// Peaks: a peak starts when ADC 1 goes above vth and ends when it falls below
// vth - hys. Its time is the centroid of (v - vth) over the samples above vth,
// and it counts only with at least nmin samples above vth. Peaks less than tmin
// after the first one are ignored.
//
// States: OFF (lock != 1, output 0 V), HOLD (output frozen), LOCKED.
//   A sweep with no pair, or with |err| >= win, is skipped and the output held.
//   nbad skipped sweeps in a row: LOCKED -> HOLD (an unlock; integ set to 0).
//   ngood good sweeps in a row: HOLD -> LOCKED.
//   hold = 0: no window, never HOLD; every pair is used.
//   override = 1: output = ovolt, state HOLD, PI frozen. When it is released with
//   the lock on, the lock relocks after ngood good sweeps starting from ovolt.
//
// Serial: send "name" to read a value, "name value" to set it.
//   settings:  lock hold setp vth hys nmin tmin win nbad ngood g1 p1 i1
//              override ovolt fmt
//   read only: sep integ state tfirst h1 h2 bad bad_none bad_one bad_win
//              unlocks sats period nopair
//   commands:  clear (integ and output to 0 V, state kept), ping (board name)
// A reflash restores the defaults below.
//
// Printout every ~10 sweeps. fmt 1: one readable line. fmt 0: CSV, read by the
// dashboard's FP lock server (waxx/util/guis/fp_lock), columns
//   sep, err, out, state, tfirst, h1, h2, bad, unlocks, sats, saturated,
//   bad_none, bad_one, bad_win, integ, period, nopair
// (only ever append columns). Any other fmt: no printout.
// sep, tfirst, h1, h2 are from the last sweep that found a pair; nopair is the
// number of sweeps since then without one; err = sep - setp (current setp).
//
// The previous firmware (pid_frequency_stabilize_Raman) is in
// ../pid_frequency_stabilize_Raman.7z.

#include "qCommand.h"
qCommand qC;
IntervalTimer lockTimer;

// ---- settings ----
double lock = 1;        // 1 = lock on; anything else = off, output 0 V
int32_t hold = 1;       // 1 = skip bad sweeps and pause in HOLD; 0 = use every pair
double setp = 5.5;      // ms, peak separation setpoint
double vth = 3.0;       // V, peak threshold
double hys = 0.2;       // V, a peak ends below vth - hys
int32_t nmin = 1;       // samples above vth for a peak to count
double tmin = 2.5;      // ms, ignore peaks closer than this to the first
double win = 30.0;      // ms, |err| >= win skips the sweep
int32_t nbad = 5;       // skipped sweeps in a row: LOCKED -> HOLD
int32_t ngood = 10;     // good sweeps in a row: HOLD -> LOCKED
double g1 = -1.0;        // overall gain
double p1 = -0.01;      // V/ms, proportional gain
double i1 = -0.01;      // V/ms per sweep, integral gain
int32_t override = 0;   // 1 = output forced to ovolt
double ovolt = 0.0;     // V, the forced output
int32_t fmt = 1;        // printout: 1 = readable, 0 = CSV, else none

const double RAIL = 9.5;      // V, limit on the output and integ
const double DAC_MAX = 10.0;  // V, limit on ovolt
const int UPDATE_US = 2;      // lock update period (the ADC samples every 1 us)

enum State : int32_t { OFF = 0, HOLD = 1, LOCKED = 2 };

// ---- what the lock reports (written in the timer interrupt) ----
struct Status {
  double sep = 0;         // ms, separation of the last pair
  double tfirst = 0;      // ms, that pair's first peak after the trigger edge
  double h1 = 0, h2 = 0;  // V, that pair's peak heights
  double out = 0;         // V, DAC 1
  double integ = 0;       // V, integrator
  double period = 0;      // ms, sweep period
  int32_t state = HOLD;
  int32_t saturated = 0;  // 1 while the output or integ is at the rail
  uint32_t bad = 0;       // skipped sweeps = bad_none + bad_one + bad_win
  uint32_t bad_none = 0;  //   no peak
  uint32_t bad_one = 0;   //   first peak only
  uint32_t bad_win = 0;   //   pair found, |err| >= win
  uint32_t unlocks = 0;   // LOCKED -> HOLD
  uint32_t sats = 0;      // times the output reached the rail
  uint32_t nopair = 0;    // sweeps in a row without a pair
};
Status st;

// ---- bookkeeping inside a sweep (timer interrupt only) ----
volatile double adc_volts = 0;
double dac_volts = 0;           // last value written to DAC 1
bool last_trig = false;
bool sweep_started = false;     // false until the first trigger edge
uint32_t t_edge = 0;            // us, micros() at this sweep's trigger edge
int n_peaks = 0;                // peaks found this sweep: 0, 1, or 2 (pair found)
double t_peak1 = 0, h_peak1 = 0;
int good_run = 0, bad_run = 0;  // good / skipped sweeps in a row
bool in_peak = false;           // the peak being measured:
double w_sum = 0, wt_sum = 0;   //   sums of (v - vth) and (v - vth)*t
double v_max = 0;
int n_above = 0;

void setup() {
  Serial.begin(115200);
  configureADC(1, 1, 0, BIPOLAR_10V, readADC);
  writeDAC(1, 0);

  qC.assignVariable("lock", &lock);
  qC.assignVariable("hold", &hold);
  qC.assignVariable("setp", &setp);
  qC.assignVariable("vth", &vth);
  qC.assignVariable("hys", &hys);
  qC.assignVariable("nmin", &nmin);
  qC.assignVariable("tmin", &tmin);
  qC.assignVariable("win", &win);
  qC.assignVariable("nbad", &nbad);
  qC.assignVariable("ngood", &ngood);
  qC.assignVariable("g1", &g1);
  qC.assignVariable("p1", &p1);
  qC.assignVariable("i1", &i1);
  qC.assignVariable("override", &override);
  qC.assignVariable("ovolt", &ovolt);
  qC.assignVariable("fmt", &fmt);

  qC.assignVariable("sep", &st.sep, true);
  qC.assignVariable("integ", &st.integ, true);
  qC.assignVariable("state", &st.state, true);
  qC.assignVariable("tfirst", &st.tfirst, true);
  qC.assignVariable("h1", &st.h1, true);
  qC.assignVariable("h2", &st.h2, true);
  qC.assignVariable("bad", &st.bad, true);
  qC.assignVariable("bad_none", &st.bad_none, true);
  qC.assignVariable("bad_one", &st.bad_one, true);
  qC.assignVariable("bad_win", &st.bad_win, true);
  qC.assignVariable("unlocks", &st.unlocks, true);
  qC.assignVariable("sats", &st.sats, true);
  qC.assignVariable("period", &st.period, true);
  qC.assignVariable("nopair", &st.nopair, true);

  qC.addCommand("clear", clearOutput);
  qC.addCommand("ping", ping);

  lockTimer.begin(update, UPDATE_US);
}

void readADC() {
  adc_volts = readADC1_from_ISR();
}

// The lock: runs every UPDATE_US.
void update() {
  noInterrupts();
  const double v = adc_volts;
  interrupts();
  const uint32_t now = micros();
  const bool trig = triggerRead(1);

  applySwitches();
  if (trig && !last_trig) newSweep(now);
  last_trig = trig;
  if (sweep_started) findPeak(now - t_edge, v);

  if (st.out != dac_volts) {
    writeDAC(1, st.out);
    dac_volts = st.out;
  }
}

// lock and override take effect at once
void applySwitches() {
  if (override == 1) {
    st.state = HOLD;
    st.out = clamp(ovolt, DAC_MAX);
    st.integ = clamp(st.out, RAIL);  // the relock after release starts here
    st.saturated = 0;
    good_run = 0;
    bad_run = 0;
  } else if (lock != 1) {
    st.state = OFF;
    st.out = 0;
    st.integ = 0;
    st.saturated = 0;
  } else if (st.state == OFF) {
    st.state = HOLD;
    good_run = 0;
    bad_run = 0;
  }
}

// Trigger rising edge: the previous sweep is over, a new one starts.
void newSweep(uint32_t now) {
  if (sweep_started) {
    st.period = (now - t_edge) / 1000.0;
    if (n_peaks < 2) {
      st.nopair++;
      skipSweep(n_peaks == 0 ? st.bad_none : st.bad_one);
    }
  }
  sweep_started = true;
  t_edge = now;
  n_peaks = 0;
  in_peak = false;  // a peak across the edge is dropped
}

// One ADC sample, t_us after the trigger edge.
void findPeak(uint32_t t_us, double v) {
  if (v > vth) {
    if (!in_peak) {
      in_peak = true;
      w_sum = 0;
      wt_sum = 0;
      v_max = 0;
      n_above = 0;
    }
    const double w = v - vth;
    w_sum += w;
    wt_sum += w * t_us;
    n_above++;
    if (v > v_max) v_max = v;
  } else if (in_peak && v < vth - hys) {
    in_peak = false;
    if (n_above >= nmin) peakFound(wt_sum / w_sum / 1000.0, v_max);
  }
}

// A peak at t_ms after the trigger edge, height h volts.
void peakFound(double t_ms, double h) {
  if (n_peaks == 0) {
    t_peak1 = t_ms;
    h_peak1 = h;
    n_peaks = 1;
  } else if (n_peaks == 1 && t_ms - t_peak1 > tmin) {
    n_peaks = 2;
    st.sep = t_ms - t_peak1;
    st.tfirst = t_peak1;
    st.h1 = h_peak1;
    st.h2 = h;
    st.nopair = 0;
    piStep(st.sep - setp);
  }
}

// Once per sweep with a pair.
void piStep(double err) {
  if (hold && !(fabs(err) < win)) {
    skipSweep(st.bad_win);
    return;
  }
  if (st.state == OFF || override == 1) return;  // measured, not applied
  bad_run = 0;
  if (st.state == HOLD) {
    if (hold && ++good_run < ngood) return;
    st.state = LOCKED;
  }
  st.integ = clamp(st.integ + g1 * i1 * err, RAIL);
  const double raw = g1 * p1 * err + st.integ;
  st.out = clamp(raw, RAIL);
  const int32_t sat = (st.out != raw) || (fabs(st.integ) >= RAIL);
  if (sat && !st.saturated) st.sats++;
  st.saturated = sat;
}

// A sweep with no usable pair: the output is held.
void skipSweep(uint32_t& reason) {
  st.bad++;
  reason++;
  good_run = 0;
  if (hold && st.state == LOCKED && ++bad_run >= nbad) {
    st.state = HOLD;
    st.unlocks++;
    bad_run = 0;
    st.integ = 0;  // the relock starts the integrator from 0
  }
}

double clamp(double x, double limit) {
  if (x > limit) return limit;
  if (x < -limit) return -limit;
  return x;
}

void clearOutput(qCommand& qC, Stream& S) {
  noInterrupts();
  st.integ = 0;
  st.out = 0;
  st.saturated = 0;
  interrupts();
  S.println("integral and output cleared (0 V); state unchanged");
}

struct Cal {
  uint16_t cal_a;
  double cal_b;
  uint16_t cal_c;
  char cal_d[16];
};

// prints the board's stored name
void ping(qCommand& qC, Stream& S) {
  struct Cal cal;
  readNVMblock(&cal, sizeof(cal), 0xFA00);
  Serial.println(cal.cal_d);
}

void loop() {
  static unsigned long last_print = 0;
  qC.readSerial(Serial);

  // print every ~10 sweeps
  if (millis() - last_print < 10 * (st.period > 1 ? st.period : 1)) return;
  last_print = millis();
  toggleLEDGreen();

  noInterrupts();
  const Status s = st;  // a copy, so one line never mixes two sweeps
  interrupts();
  const double err = s.sep > 0 ? s.sep - setp : 0;

  if (fmt == 0) {
    Serial.printf("%.3f, %.3f, %.4f, %ld, %.3f, %.3f, %.3f, %lu, %lu, %lu, %ld, %lu, %lu, %lu, %.4f, %.3f, %lu\n",
                  s.sep, err, s.out, s.state, s.tfirst, s.h1, s.h2, s.bad, s.unlocks, s.sats,
                  s.saturated, s.bad_none, s.bad_one, s.bad_win, s.integ, s.period, s.nopair);
  } else if (fmt == 1) {
    const char* state = override == 1     ? "OVERRIDE"
                        : s.state == LOCKED ? "LOCKED"
                        : s.state == HOLD   ? "HOLD"
                                            : "OFF";
    Serial.printf("%-8s sep %7.3f ms  err %+7.3f ms  out %+7.4f V%s  integ %+7.4f V  "
                  "peak 1 at %7.3f ms  h1 %5.2f V  h2 %5.2f V  "
                  "skipped %lu (none %lu, 1 peak %lu, win %lu)  unlocks %lu  rail %lu  nopair %lu\n",
                  state, s.sep, err, s.out, s.saturated ? " RAIL" : "", s.integ,
                  s.tfirst, s.h1, s.h2,
                  s.bad, s.bad_none, s.bad_one, s.bad_win, s.unlocks, s.sats, s.nopair);
  }
}
