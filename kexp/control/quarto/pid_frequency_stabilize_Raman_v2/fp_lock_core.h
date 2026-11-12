// fp_lock_core.h -- peak-separation lock for a scanning Fabry-Perot cavity.
//
// Measures the time between the first two transmission peaks after each rising
// edge of the scan trigger and servos it to a setpoint. Pure C++ with no
// Arduino calls, so the same code runs in the offline test
// (k-exp/tests/test_fp_lock_core.py).
//
// Changes from pid_frequency_stabilize_Raman.ino:
//  - peak time = centroid of (v - vth) over the samples above vth, with
//    hysteresis (a peak ends below vth - hys) and a minimum width (nmin);
//    unbiased for a symmetric peak, whatever its height
//  - a sweep is rejected (no update, output held) when no pair is found or
//    |err| >= win; nbad rejected sweeps in a row while LOCKED -> HOLD
//  - HOLD keeps the output where it is and re-locks by itself after ngood
//    good sweeps in a row; at the relock the integral is cleared, so the
//    output steps from the held value to g1*(p1 + i1)*err (except the first
//    relock after an override, see below)
//  - PI: integral += g1*i1*err, feedback = g1*p1*err + integral. In the old
//    code p1 acted as the integral gain, i1 as a double integral and d1 as
//    proportional: the old default p1 = -0.01 is the new i1 = -0.01. No
//    derivative term. The output and the integral are clamped at +/-rail and
//    stay there (the old code snapped to 0 V)
//  - hold = 0 turns the gate and the pause off: every pair is used whatever
//    its error and the state never leaves LOCKED (sweeps with no pair still
//    cannot move the output). Only the +/-rail clamp then limits a wrong
//    pairing.
//  - integer microsecond timestamps with unsigned differences (micros() wrap)
//  - override = 1 sets the output to ovolt and the state to HOLD, whether the
//    lock is on or off. The PI is frozen (no integral update, so no windup); sweeps are
//    still measured (sep, err, bad counts) and it is not counted as an unlock.
//    Released with the lock on: HOLD at ovolt, re-locks after ngood good sweeps
//    (at the next pair with hold = 0) with the integral STARTING AT THE HELD
//    OUTPUT (ovolt, clamped to +/-rail), so the lock takes over from the
//    override voltage instead of stepping to ~0 V. Only that first relock is
//    seeded; later relocks (after a dropout) clear the integral as usual. With
//    the lock off: OFF, 0 V, and nothing is seeded.
//  - the printed peak values all describe one sweep: tFirst, h1, sep and h2
//    are committed together when a pair completes (the first peak of a sweep
//    without a pair is not reported), nNoPair counts the completed sweeps in a
//    row without a pair (how old they are), and errNow() = sep - setp against
//    the current setpoint. The bad-sweep counters count in every state (OFF
//    included); only LOCKED -> HOLD depends on the state.
#pragma once
#include <stdint.h>
#include <math.h>

namespace fplock {

enum State : int32_t { OFF = 0, HOLD = 1, LOCKED = 2 };

struct Settings {
  double lock = 1;       // 1 = lock on; anything else = off, output 0 V
  int32_t hold = 1;      // 1 = gate on win and pause in HOLD; 0 = use every pair, never HOLD
  double vth = 3.0;      // V, peak threshold
  double hys = 0.2;      // V, a peak ends when v < vth - hys
  int32_t nmin = 2;      // samples above vth for a peak to count (x the sketch's UPDATE_US)
  double tmin = 2.5;     // ms, peaks closer than this to the first are ignored
  double setp = 5.5;     // ms, separation setpoint
  double win = 15.0;      // ms, |err| >= win rejects the sweep
  int32_t nbad = 5;      // rejected sweeps in a row: LOCKED -> HOLD
  int32_t ngood = 10;    // good sweeps in a row: HOLD -> LOCKED
  double g1 = 1.0;       // overall gain
  double p1 = -0.01;       // V/ms, proportional
  double i1 = -0.01;     // V/ms per sweep, integral (the old p1 did this)
  double rail = 8.0;     // V, output and integral clamp
  int32_t override = 0;  // 1 = output set to ovolt, state HOLD, PI frozen (integral does not wind)
  double ovolt = 0.0;    // V, forced output while override = 1
};

constexpr double kDacMax = 10.0;  // V, the output is clamped to +/-kDacMax (assumed DAC range)

class Lock {
public:
  Settings s;

  // last pair (sep, tFirst, h1, h2 all from the same sweep), for printing
  double sep = 0;        // ms
  double err = 0;        // ms, sep - setp when the pair was measured (what the PI used)
  double feedback = 0;   // V
  double integral = 0;   // V
  double tFirst = 0;     // ms, the pair's first peak after the trigger edge
  double h1 = 0, h2 = 0; // V, the pair's peak heights
  uint32_t nNoPair = 0;  // completed sweeps in a row without a pair (0 = the last sweep had one)
  double period = 0;     // ms, trigger period
  int32_t state = HOLD;
  int32_t saturated = 0;
  uint32_t nSweeps = 0, nBad = 0, nUnlock = 0, nSat = 0;
  // nBad split by reason: no peak found / only one peak (no second at least
  // tmin later) / pair found but |err| >= win. They sum to nBad.
  uint32_t nBadNone = 0, nBadOne = 0, nBadWin = 0;

  // Zero the integral and the output; the state and the sweep counters are kept.
  // The caller writes the 0 V to the DAC.
  void clearOutput() {
    integral = 0;
    feedback = 0;
    saturated = 0;
  }

  // The last pair's separation against the current setpoint (0 before any pair).
  // err keeps the error the PI used; after a setp change only this one is current.
  double errNow() const { return sep > 0 ? sep - s.setp : 0; }

  // Volts the DAC should hold: ovolt while override = 1 (clamped to +/-kDacMax),
  // otherwise the lock's feedback. step() also copies ovolt into feedback under
  // override; this gives the same value before the first sample is taken.
  double outputVolts() const {
    if (s.override != 1) return feedback;
    return overrideVolts();
  }

  // One ADC sample. Returns true when the DAC output should be rewritten.
  bool step(uint32_t tUs, double v, bool trig) {
    bool write = false;

    if (s.override == 1) {
      // output = ovolt, state HOLD, PI frozen; not an unlock
      if (state != HOLD) state = HOLD;
      seedHeld = true;   // the relock after the release starts from this output
      goodRun = 0;
      badRun = 0;
      saturated = 0;
      const double u = overrideVolts();
      if (u != feedback) {
        feedback = u;
        write = true;
      }
    } else if (s.lock != 1) {
      seedHeld = false;
      if (state != OFF) {
        state = OFF;
        feedback = 0;
        integral = 0;
        saturated = 0;
        write = true;
      }
    } else if (state == OFF) {
      state = HOLD;
      goodRun = 0;
      badRun = 0;
    }

    if (trig && !lastTrig) {
      // rising edge: a new sweep starts
      if (haveEdge) {
        period = (uint32_t)(tUs - tEdge) / 1000.0;
        nSweeps++;
        if (!measured) {
          nNoPair++;
          reject(nPeaks == 0 ? &nBadNone : &nBadOne);
        }
      }
      haveEdge = true;
      tEdge = tUs;
      nPeaks = 0;
      measured = false;
      inPeak = false;   // a peak straddling the edge is dropped
    }
    lastTrig = trig;
    if (!haveEdge) return write;

    if (!inPeak) {
      if (v > s.vth) {
        inPeak = true;
        pBase = tUs;
        pS0 = pS1 = 0;
        pN = 0;
        pMax = v;
        accumulate(tUs, v);
      }
    } else if (v > s.vth) {
      accumulate(tUs, v);
    } else if (v < s.vth - s.hys) {
      inPeak = false;
      if (pN >= s.nmin && pS0 > 0) write |= onPeak(pBase, pS1 / pS0, pMax);
    }
    return write;
  }

private:
  bool lastTrig = false, haveEdge = false, measured = false, inPeak = false;
  bool seedHeld = false;   // set by override: the next relock starts the integral at the held output
  uint32_t tEdge = 0;
  int32_t nPeaks = 0, goodRun = 0, badRun = 0;
  // peak being integrated: time = pBase + pS1/pS0 (us)
  uint32_t pBase = 0;
  double pS0 = 0, pS1 = 0, pMax = 0;
  int32_t pN = 0;
  // first peak of the sweep (a candidate: reported only once its pair completes)
  uint32_t aBase = 0;
  double aOff = 0;
  double aT = 0, aH = 0;   // ms after the edge, V

  void accumulate(uint32_t tUs, double v) {
    const double w = v - s.vth;
    if (w <= 0) return;
    pS0 += w;
    pS1 += w * (double)(uint32_t)(tUs - pBase);
    pN++;
    if (v > pMax) pMax = v;
  }

  bool onPeak(uint32_t base, double off, double h) {
    if (measured) return false;
    if (nPeaks == 0) {
      aBase = base;
      aOff = off;
      aH = h;
      aT = ((double)(uint32_t)(base - tEdge) + off) / 1000.0;
      nPeaks = 1;
      return false;
    }
    const double dtUs = (double)(uint32_t)(base - aBase) + (off - aOff);
    if (dtUs <= s.tmin * 1000.0) return false;
    nPeaks++;
    measured = true;
    // commit the pair: every printed peak value comes from this sweep
    tFirst = aT;
    h1 = aH;
    h2 = h;
    sep = dtUs / 1000.0;
    nNoPair = 0;
    return onMeasurement();
  }

  bool onMeasurement() {
    err = sep - s.setp;
    if (s.hold && !(fabs(err) < s.win)) {
      reject(&nBadWin);   // counted in every state
      return false;
    }
    if (state == OFF) return false;
    if (s.override == 1) return false;  // measured and counted, never applied
    badRun = 0;
    if (state == HOLD) {
      if (s.hold && ++goodRun < s.ngood) return false;
      state = LOCKED;
      // relock: after an override the integral starts at the held output
      // (ovolt, clamped to +/-rail); otherwise it restarts from zero, so the
      // output steps from the held value to g1*(p1 + i1)*err
      integral = seedHeld ? clamp(feedback) : 0;
      seedHeld = false;
    }
    integral = clamp(integral + s.g1 * s.i1 * err);
    const double raw = s.g1 * s.p1 * err + integral;
    const double u = clamp(raw);
    const int32_t sat = (u != raw) || (fabs(integral) >= s.rail);
    if (sat && !saturated) nSat++;
    saturated = sat;
    feedback = u;
    return true;
  }

  double overrideVolts() const {
    return s.ovolt > kDacMax ? kDacMax : (s.ovolt < -kDacMax ? -kDacMax : s.ovolt);
  }

  double clamp(double x) const {
    return x > s.rail ? s.rail : (x < -s.rail ? -s.rail : x);
  }

  // sweep without a usable pair: output held. Counted in every state; only a
  // LOCKED lock can fall to HOLD.
  void reject(uint32_t* reasonCount) {
    nBad++;
    (*reasonCount)++;
    goodRun = 0;
    if (s.hold && state == LOCKED && ++badRun >= s.nbad) {
      state = HOLD;
      nUnlock++;
      badRun = 0;
    }
  }
};

}  // namespace fplock
