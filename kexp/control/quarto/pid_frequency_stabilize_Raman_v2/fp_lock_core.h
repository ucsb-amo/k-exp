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
//    good sweeps in a row
//  - PI: integral += g1*i1*err, feedback = g1*p1*err + integral. In the old
//    code p1 acted as the integral gain, i1 as a double integral and d1 as
//    proportional: the old default p1 = -0.01 is the new i1 = -0.01. No
//    derivative term. The output and the integral are clamped at +/-rail and
//    stay there (the old code snapped to 0 V)
//  - integer microsecond timestamps with unsigned differences (micros() wrap)
#pragma once
#include <stdint.h>
#include <math.h>

namespace fplock {

enum State : int32_t { OFF = 0, HOLD = 1, LOCKED = 2 };

struct Settings {
  double lock = 1;       // 1 = lock on; anything else = off, output 0 V
  double vth = 3.0;      // V, peak threshold
  double hys = 0.2;      // V, a peak ends when v < vth - hys
  int32_t nmin = 3;      // samples above vth for a peak to count (4 x 3 us = 12 us)
  double tmin = 1.5;     // ms, peaks closer than this to the first are ignored
  double setp = 6.4;    // ms, separation setpointd
  double win = 1.0;      // ms, |err| >= win rejects the sweep
  int32_t nbad = 5;      // rejected sweeps in a row: LOCKED -> HOLD
  int32_t ngood = 10;    // good sweeps in a row: HOLD -> LOCKED
  double g1 = 1.0;       // overall gain
  double p1 = 0.0;       // V/ms, proportional
  double i1 = -0.01;     // V/ms per sweep, integral (the old p1 did this)
  double rail = 1.5;     // V, output and integral clamp
};

class Lock {
public:
  Settings s;

  // last result, for printing
  double sep = 0;        // ms
  double err = 0;        // ms
  double feedback = 0;   // V
  double integral = 0;   // V
  double tFirst = 0;     // ms, first peak after the trigger edge
  double h1 = 0, h2 = 0; // V, peak heights
  double period = 0;     // ms, trigger period
  int32_t state = HOLD;
  int32_t saturated = 0;
  uint32_t nSweeps = 0, nBad = 0, nUnlock = 0, nSat = 0;
  // nBad split by reason: no peak found / only one peak (no second at least
  // tmin later) / pair found but |err| >= win. They sum to nBad.
  uint32_t nBadNone = 0, nBadOne = 0, nBadWin = 0;

  // One ADC sample. Returns true when the DAC output should be rewritten.
  bool step(uint32_t tUs, double v, bool trig) {
    bool write = false;

    if (s.lock != 1) {
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
        if (!measured) reject(nPeaks == 0 ? &nBadNone : &nBadOne);
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
  uint32_t tEdge = 0;
  int32_t nPeaks = 0, goodRun = 0, badRun = 0;
  // peak being integrated: time = pBase + pS1/pS0 (us)
  uint32_t pBase = 0;
  double pS0 = 0, pS1 = 0, pMax = 0;
  int32_t pN = 0;
  // first peak of the sweep
  uint32_t aBase = 0;
  double aOff = 0;

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
      h1 = h;
      tFirst = ((double)(uint32_t)(base - tEdge) + off) / 1000.0;
      nPeaks = 1;
      return false;
    }
    const double dtUs = (double)(uint32_t)(base - aBase) + (off - aOff);
    if (dtUs <= s.tmin * 1000.0) return false;
    nPeaks++;
    h2 = h;
    measured = true;
    sep = dtUs / 1000.0;
    return onMeasurement();
  }

  bool onMeasurement() {
    err = sep - s.setp;
    if (state == OFF) return false;
    if (!(fabs(err) < s.win)) {
      reject(&nBadWin);
      return false;
    }
    badRun = 0;
    if (state == HOLD) {
      if (++goodRun < s.ngood) return false;
      state = LOCKED;
      // bumpless: the first output after HOLD equals the held output
      integral = feedback - s.g1 * s.p1 * err;
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

  double clamp(double x) const {
    return x > s.rail ? s.rail : (x < -s.rail ? -s.rail : x);
  }

  // sweep without a usable pair: output held
  void reject(uint32_t* reasonCount) {
    if (state == OFF) return;
    nBad++;
    (*reasonCount)++;
    goodRun = 0;
    if (state == LOCKED && ++badRun >= s.nbad) {
      state = HOLD;
      nUnlock++;
      badRun = 0;
    }
  }
};

}  // namespace fplock
