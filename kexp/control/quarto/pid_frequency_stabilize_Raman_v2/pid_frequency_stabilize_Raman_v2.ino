// Raman laser lock: peak separation on the scanning Fabry-Perot cavity.
// Replaces pid_frequency_stabilize_Raman (archived in
// ../pid_frequency_stabilize_Raman.7z, to reflash it). The lock logic is in
// fp_lock_core.h; the changes are listed at its top.
//
// Serial commands (send a name alone to read it, "name value" to set it):
//   lock       1 = on; anything else = off, output 0 V
//   hold       1 = gate on win and pause in HOLD (default); 0 = use every
//              pair and never pause
//   setp      ms, separation setpoint
//   vth hys    V, peak threshold; a peak ends below vth - hys
//   nmin       samples (UPDATE_US each) above vth for a peak to count
//   tmin       ms, peaks closer than this to the first are ignored
//   win        ms, |err| >= win rejects the sweep (output held)
//   nbad       rejected sweeps in a row before LOCKED -> HOLD
//   ngood      good sweeps in a row before HOLD -> LOCKED
//   g1 p1 i1   gain, proportional, integral:
//              integral += g1*i1*err, feedback = g1*p1*err + integral
//   fmt        printout: 1 = table (default), 0 = CSV, 2 = paused
//   read only: sep, integ, state (0 off, 1 hold, 2 locked), tfirst, h1, h2,
//              bad (rejected sweeps) = bad_none + bad_one + bad_win,
//              unlocks, sats (times at the rail)
//   clear      zero the integral and the output (0 V), keep the state
//   help       lists all of the above with their current values
// Printed every ~10 sweeps. fmt 1: a table with a header every 20 rows and a
// "##" line when the state or a counter changes. fmt 0: CSV
//   sep, er, feedback, state, tfirst, h1, h2, bad, unlocks, sats, saturated,
//   bad_none, bad_one, bad_win, integ, period
// (the dashboard's FP lock server reads this; columns are only ever appended)
// The table's "why" column is the main reason sweeps were skipped since the
// previous row: none = no peak, 1pk = first peak only, win = pair outside win.
#include "qCommand.h"
#include "fp_lock_core.h"
qCommand qC;

struct Cal
{
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16];
};

IntervalTimer plot;
const int UPDATE_US = 2;   //lock update period; the ADC itself samples every 1 us

volatile bool trigger1Activated = false;
volatile double currentSignalValue = 0;

fplock::Lock lk;
int32_t fmt = 1;

void setup() {
  Serial.begin(115200);
  qC.addCommand("ping",ping);
  qC.addCommand("help",help);
  qC.addCommand("clear",clearIntegral);

  configureADC(1, 1, 0, BIPOLAR_10V, getADC1);

  qC.assignVariable("sep", &lk.sep, true);
  qC.assignVariable("setp", &lk.s.setp);
  qC.assignVariable("vth", &lk.s.vth);
  qC.assignVariable("hys", &lk.s.hys);
  qC.assignVariable("nmin", &lk.s.nmin);
  qC.assignVariable("tmin", &lk.s.tmin);
  qC.assignVariable("win", &lk.s.win);
  qC.assignVariable("nbad", &lk.s.nbad);
  qC.assignVariable("ngood", &lk.s.ngood);
  qC.assignVariable("g1", &lk.s.g1);
  qC.assignVariable("p1", &lk.s.p1);
  qC.assignVariable("i1", &lk.s.i1);
  qC.assignVariable("lock", &lk.s.lock);
  qC.assignVariable("hold", &lk.s.hold);
  qC.assignVariable("fmt", &fmt);
  qC.assignVariable("integ", &lk.integral, true);
  qC.assignVariable("state", &lk.state, true);
  qC.assignVariable("tfirst", &lk.tFirst, true);
  qC.assignVariable("h1", &lk.h1, true);
  qC.assignVariable("h2", &lk.h2, true);
  qC.assignVariable("bad", &lk.nBad, true);
  qC.assignVariable("bad_none", &lk.nBadNone, true);
  qC.assignVariable("bad_one", &lk.nBadOne, true);
  qC.assignVariable("bad_win", &lk.nBadWin, true);
  qC.assignVariable("unlocks", &lk.nUnlock, true);
  qC.assignVariable("sats", &lk.nSat, true);
  qC.assignVariable("period", &lk.period, true);

  writeDAC(1, 0);
  enableInterruptTrigger(1, BOTH_EDGES, hold1);
}

void ping(qCommand& qC, Stream& S)
{
  struct Cal cal2;
  readNVMblock(&cal2, sizeof(cal2), 0xFA00);
  Serial.println(cal2.cal_d);
}

// Zero the integral and the output (0 V) without changing the state; the lock
// restarts from 0 V at its next pair. The DAC is written with the update timer
// stopped so it cannot be overwritten by a stale value.
void clearIntegral(qCommand& qC, Stream& S)
{
  noInterrupts();
  lk.clearOutput();
  writeDAC(1, 0);
  interrupts();
  S.println("integral and output cleared (0 V); state unchanged");
}

const char* stateName(int32_t s) {
  return s == fplock::LOCKED ? "LOCKED" : (s == fplock::HOLD ? "HOLD" : "OFF");
}

void help(qCommand& qC, Stream& S)
{
  const fplock::Settings& s = lk.s;
  S.println("FP peak-separation lock. Send a name to read it, 'name value' to set it.");
  S.println("settings (current value):");
  S.printf("  lock   %10g          1 = on; anything else = off (0 V, integral cleared)\n", s.lock);
  S.printf("  hold   %10ld          1 = skip bad sweeps and pause in HOLD; 0 = use every pair, never pause\n",
           (long)s.hold);
  S.printf("  setp   %10.3f ms       separation setpoint\n", s.setp);
  S.printf("  p1     %10.4g V/ms     proportional: feedback = g1*p1*err + integ\n", s.p1);
  S.printf("  i1     %10.4g V/ms     integral, each sweep: integ += g1*i1*err\n", s.i1);
  S.printf("  g1     %10.4g          scales p1 and i1\n", s.g1);
  S.printf("  win    %10.3f ms       |err| >= win: sweep skipped, output held\n", s.win);
  S.printf("  nbad   %10ld sweeps   skipped in a row: LOCKED -> HOLD\n", (long)s.nbad);
  S.printf("  ngood  %10ld sweeps   good in a row: HOLD -> LOCKED\n", (long)s.ngood);
  S.printf("  vth    %10.3f V        peak threshold\n", s.vth);
  S.printf("  hys    %10.3f V        a peak ends below vth - hys\n", s.hys);
  S.printf("  nmin   %10ld samples  (%d us each) above vth for a peak to count\n", (long)s.nmin, UPDATE_US);
  S.printf("  tmin   %10.3f ms       ignore peaks closer than this to the first\n", s.tmin);
  S.printf("  fmt    %10ld          printout: 1 = table, 0 = CSV, 2 = paused\n", (long)fmt);
  S.printf("  (output limit +/-%.2f V, fixed in the code)\n", s.rail);
  S.println("read only: sep integ state tfirst h1 h2 bad unlocks sats period");
  S.println("  bad = bad_none (no peak) + bad_one (first peak only) + bad_win (pair, |err| >= win)");
  S.println("states: OFF = lock off | HOLD = output frozen, waiting for good sweeps | LOCKED");
  S.println("clear: zero the integral and the output (0 V), keep the state; ping (board label); help");
}

// The main reason sweeps were skipped since the previous row:
// "none" = no peak, "1pk" = first peak only, "win" = pair outside win, "-" = none skipped.
const char* whySince(const fplock::Lock& k) {
  static uint32_t lastNone = 0, lastOne = 0, lastWin = 0;
  const uint32_t dNone = k.nBadNone - lastNone;
  const uint32_t dOne = k.nBadOne - lastOne;
  const uint32_t dWin = k.nBadWin - lastWin;
  lastNone = k.nBadNone; lastOne = k.nBadOne; lastWin = k.nBadWin;
  if (dNone + dOne + dWin == 0) return "-";
  if (dNone >= dOne && dNone >= dWin) return "none";
  return dOne >= dWin ? "1pk" : "win";
}

void printHeader() {
  Serial.println("   sep ms    err ms     fb V  integ V  state  rail  tfirst ms  h1 V  h2 V     bad  unlk  sats  why");
}

void printRow(const fplock::Lock& k, const char* why) {
  Serial.printf("%9.3f %+9.3f %+8.4f %+8.4f  %-6s %-4s %10.3f %5.2f %5.2f %7lu %5lu %5lu  %s\n",
                k.sep, k.err, k.feedback, k.integral, stateName(k.state),
                k.saturated ? "RAIL" : "-", k.tFirst, k.h1, k.h2,
                (unsigned long)k.nBad, (unsigned long)k.nUnlock, (unsigned long)k.nSat, why);
}

void printCsv(const fplock::Lock& k) {
  Serial.printf("%.3f, %.3f, %.4f, %ld, %.3f, %.3f, %.3f, %lu, %lu, %lu, %ld, %lu, %lu, %lu, "
                "%.4f, %.3f\n",
                k.sep, k.err, k.feedback, (long)k.state, k.tFirst, k.h1, k.h2,
                (unsigned long)k.nBad, (unsigned long)k.nUnlock, (unsigned long)k.nSat,
                (long)k.saturated, (unsigned long)k.nBadNone, (unsigned long)k.nBadOne,
                (unsigned long)k.nBadWin, k.integral, k.period);
}

// a "##" line when the state changes or a counter jumps between two printouts
void printEvents(const fplock::Lock& k) {
  static int32_t lastState = -1;
  static uint32_t lastBad = 0, lastUnlock = 0, lastSat = 0;
  if (lastState >= 0 && k.state != lastState) {
    Serial.printf("## %s -> %s\n", stateName(lastState), stateName(k.state));
  }
  if (k.nUnlock != lastUnlock) {
    Serial.printf("## lost lock (%lu unlocks so far)\n", (unsigned long)k.nUnlock);
  }
  if (k.nSat != lastSat) {
    Serial.printf("## output hit the +/-%.2f V rail (%lu times so far)\n", k.s.rail,
                  (unsigned long)k.nSat);
  }
  // skipped sweeps are expected in HOLD; report them only while locked
  if (k.nBad != lastBad && lastState == fplock::LOCKED && k.state == fplock::LOCKED) {
    Serial.printf("## %lu sweep(s) skipped (no pair, or |err| >= win)\n",
                  (unsigned long)(k.nBad - lastBad));
  }
  lastState = k.state;
  lastBad = k.nBad;
  lastUnlock = k.nUnlock;
  lastSat = k.nSat;
}

void hold1() {
  if (triggerRead(1)) trigger1Activated = true;
}

void getADC1() {
  currentSignalValue = readADC1_from_ISR();
}

void update() {
  noInterrupts();
  const double v = currentSignalValue;
  interrupts();
  if (lk.step(micros(), v, triggerRead(1))) writeDAC(1, lk.feedback);
}

void loop() {
  static bool timerStarted = false;
  static unsigned long lastPrint = 0;

  if (trigger1Activated && !timerStarted) {
    plot.end();
    plot.begin(update, UPDATE_US);
    timerStarted = true;
    trigger1Activated = false;
  }

  qC.readSerial(Serial);

  const double period = lk.period;
  if (millis() - lastPrint >= 10 * (period > 1 ? period : 1)) {
    lastPrint = millis();
    // copy with the timer interrupt off so a line is never half-updated
    noInterrupts();
    const fplock::Lock snap = lk;
    interrupts();
    toggleLEDGreen();
    if (fmt == 2) {
      // printout paused
    } else if (fmt == 0) {
      printCsv(snap);
    } else {
      static int rows = 0;
      printEvents(snap);
      if (rows++ % 20 == 0) printHeader();
      printRow(snap, whySince(snap));
    }
  }
}
