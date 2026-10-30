// Offline test of the Raman FP lock logic
// (kexp/control/quarto/pid_frequency_stabilize_Raman_v2/fp_lock_core.h).
// Built and run by test_fp_lock_core.py. A synthetic triangle scan: the
// trigger is high for the up half, each laser gives one Lorentzian peak per
// half (mirrored on the way down), and the separation responds to the DAC
// output with slope kLaser (ms/V).
#include <cstdio>
#include <cmath>
#include <cstdint>
#include <random>
#include <functional>
#include "fp_lock_core.h"

static int failures = 0;
#define CHECK(cond, ...)                                              \
  do {                                                                \
    if (!(cond)) {                                                    \
      failures++;                                                     \
      std::printf("FAIL %s:%d: %s -- ", __func__, __LINE__, #cond);   \
      std::printf(__VA_ARGS__);                                       \
      std::printf("\n");                                              \
    }                                                                 \
  } while (0)

struct Sim {
  fplock::Lock lk;
  double T = 40.0;          // ms, full triangle period
  double tA = 4.0037;       // ms, laser A peak on the up half (off the sample grid)
  double sep0 = 10.0;       // ms, separation at 0 V
  double kLaser = 3.33;     // ms/V
  double hA = 8.0, hB = 7.0;
  double fwhm = 0.25;       // ms
  double noise = 0.0;       // V rms
  uint32_t tUs;
  uint32_t dtUs = 2;        // the sketch's UPDATE_US
  std::mt19937 rng{12345};
  int nWrites = 0;
  double maxStep = 0;       // largest change of the output in one write

  // The tests pin every setting they depend on, so retuning the device's
  // defaults in fp_lock_core.h (setp, vth, nmin, ...) cannot change them.
  explicit Sim(uint32_t t0 = 1000) : tUs(t0) {
    fplock::Settings& s = lk.s;
    s.lock = 1;
    s.vth = 4.0;  s.hys = 0.2;  s.nmin = 3;  s.tmin = 2.0;
    s.setp = 10.0;  s.win = 1.0;  s.nbad = 5;  s.ngood = 10;
    s.g1 = 1.0;  s.p1 = 0.0;  s.i1 = -0.01;  s.rail = 1.5;
  }

  double sepTrue() const { return sep0 + kLaser * lk.feedback; }

  static double lor(double t, double tc, double h, double w) {
    const double x = 2 * (t - tc) / w;
    return h / (1 + x * x);
  }

  // perSweep(i) runs before sweep i; perMeas() after each measurement
  void run(int nSweeps, const std::function<void(int)>& perSweep = nullptr) {
    std::normal_distribution<double> n01(0, 1);
    const int steps = (int)std::lround(T * 1000 / dtUs);
    for (int i = 0; i < nSweeps; i++) {
      if (perSweep) perSweep(i);
      for (int k = 0; k < steps; k++) {
        const double t = k * dtUs / 1000.0;
        const double tB = tA + sepTrue();
        double v = lor(t, tA, hA, fwhm) + lor(t, tB, hB, fwhm)
                 + lor(t, T - tA, hA, fwhm) + lor(t, T - tB, hB, fwhm);
        if (noise > 0) v += noise * n01(rng);
        const bool trig = t < T / 2;
        const double before = lk.feedback;
        if (lk.step(tUs, v, trig)) {
          nWrites++;
          maxStep = std::fmax(maxStep, std::fabs(lk.feedback - before));
        }
        tUs += dtUs;
      }
    }
  }
};

// separation measured without feedback, against the true value
static void test_centroid_accuracy() {
  for (double hA : {4.5, 6.0, 8.0, 9.5}) {
    Sim s;
    s.lk.s.lock = 0;
    s.hA = hA;
    s.sep0 = 10.0063;
    double worst = 0;
    s.run(20, [&](int i) { if (i > 0) worst = std::fmax(worst, std::fabs(s.lk.sep - s.sep0)); });
    CHECK(worst < 2e-3, "hA %.1f: |sep - true| up to %.2f us", hA, worst * 1e3);
    std::printf("centroid hA %.1f V: |sep - true| up to %.3f us\n", hA, worst * 1e3);
  }
}

// with noise: one peak per laser, and the mean is unbiased whatever the height
static void test_noise_and_height() {
  double means[2];
  int idx = 0;
  for (double hA : {5.0, 9.0}) {
    Sim s;
    s.lk.s.lock = 1;
    s.lk.s.i1 = 0;
    s.lk.s.win = 0.5;
    s.noise = 0.05;
    s.hA = hA;
    double sum = 0;
    int n = 0;
    s.run(200, [&](int i) { if (i > 0) { sum += s.lk.sep; n++; } });
    means[idx++] = sum / n;
    CHECK(s.lk.nBad == 0, "hA %.1f: %u rejected sweeps with 0.05 V noise", hA, s.lk.nBad);
    CHECK(std::fabs(sum / n - s.sep0) < 2e-3, "hA %.1f: mean sep off by %.2f us", hA,
          (sum / n - s.sep0) * 1e3);
  }
  CHECK(std::fabs(means[0] - means[1]) < 2e-3, "height changes the mean by %.2f us",
        (means[0] - means[1]) * 1e3);
}

static void test_lock_converges() {
  Sim s;
  s.sep0 = 10.5;   // 0.5 ms off, inside win = 1 ms
  s.run(400);
  CHECK(s.lk.state == fplock::LOCKED, "state %d", s.lk.state);
  CHECK(std::fabs(s.lk.err) < 0.01, "err %.4f ms", s.lk.err);
  CHECK(std::fabs(s.sepTrue() - 10.0) < 0.01, "true sep %.4f ms", s.sepTrue());
  CHECK(s.lk.nUnlock == 0, "unlocks %u", s.lk.nUnlock);
}

// laser A's peak falls below vth: the pairing goes wrong, the output must hold,
// and the lock must come back by itself without a jump
static void test_dropout_holds_and_relocks() {
  Sim s;
  s.sep0 = 10.3;
  s.run(400);
  const double fbBefore = s.lk.feedback;
  const int writesBefore = s.nWrites;
  s.hA = 2.0;
  s.run(30);
  CHECK(s.lk.state == fplock::HOLD, "state %d during dropout", s.lk.state);
  CHECK(s.lk.nUnlock == 1, "unlocks %u", s.lk.nUnlock);
  CHECK(s.lk.feedback == fbBefore, "output moved %.5f -> %.5f", fbBefore, s.lk.feedback);
  CHECK(s.nWrites == writesBefore, "%d writes during dropout", s.nWrites - writesBefore);
  s.hA = 8.0;
  s.run(30);
  CHECK(s.lk.state == fplock::LOCKED, "state %d after recovery", s.lk.state);
  CHECK(std::fabs(s.lk.feedback - fbBefore) < 1e-3, "output jumped %.5f -> %.5f",
        fbBefore, s.lk.feedback);
}

// a single bad sweep is skipped without unlocking
static void test_single_glitch() {
  Sim s;
  s.run(200);
  const double fb = s.lk.feedback;
  s.run(1, [&](int) { s.sep0 += 3.0; });
  CHECK(s.lk.feedback == fb, "output moved on a rejected sweep");
  s.run(1, [&](int) { s.sep0 -= 3.0; });
  CHECK(s.lk.state == fplock::LOCKED, "state %d", s.lk.state);
  CHECK(s.lk.nBad == 1, "bad %u", s.lk.nBad);
  CHECK(s.lk.nUnlock == 0, "unlocks %u", s.lk.nUnlock);
}

// steady drift beyond the rail: clamp and stay there, never snap to 0 V
static void test_rail_clamps() {
  Sim s;
  s.run(100);
  double minFb = 0;
  bool sawZeroAfterRail = false;
  bool atRail = false;
  s.run(800, [&](int) {
    s.sep0 += 0.02;
    if (std::fabs(s.lk.feedback) >= s.lk.s.rail) atRail = true;
    if (atRail && s.lk.feedback == 0) sawZeroAfterRail = true;
    minFb = std::fmin(minFb, s.lk.feedback);
  });
  CHECK(atRail, "never reached the rail (min %.3f V)", minFb);
  CHECK(minFb >= -s.lk.s.rail, "output %.3f V beyond the rail", minFb);
  CHECK(!sawZeroAfterRail, "output snapped to 0 V");
  CHECK(s.lk.feedback == -s.lk.s.rail, "output %.3f V, expected held at the rail", s.lk.feedback);
  CHECK(s.lk.nSat == 1, "sats %u", s.lk.nSat);
  CHECK(s.lk.state == fplock::HOLD, "state %d (err %.2f ms)", s.lk.state, s.lk.err);
  CHECK(s.maxStep < 0.05, "largest output step %.3f V", s.maxStep);
}

static void test_lock_switch() {
  Sim s;
  s.sep0 = 10.3;
  s.run(400);
  CHECK(s.lk.feedback != 0, "lock never acted");
  s.lk.s.lock = 0;
  s.run(5);
  CHECK(s.lk.state == fplock::OFF && s.lk.feedback == 0, "state %d fb %.4f", s.lk.state, s.lk.feedback);
  s.lk.s.lock = 1;
  s.run(5);
  CHECK(s.lk.state == fplock::HOLD, "state %d after lock 1 (needs ngood sweeps)", s.lk.state);
  s.run(400);
  CHECK(s.lk.state == fplock::LOCKED && std::fabs(s.lk.err) < 0.01, "state %d err %.4f",
        s.lk.state, s.lk.err);
}

// micros() wraps every 71.6 min
static void test_micros_wrap() {
  Sim s(0xFFFFFFFFu - 200000u);
  s.lk.s.i1 = 0;
  double worst = 0;
  s.run(20, [&](int i) { if (i > 0) worst = std::fmax(worst, std::fabs(s.lk.sep - s.sep0)); });
  CHECK(s.lk.nBad == 0, "bad %u across the wrap", s.lk.nBad);
  CHECK(worst < 1e-3, "|sep - true| up to %.2f us across the wrap", worst * 1e3);
}

// feedback = g1*p1*err + integral, integral += g1*i1*err (plant disconnected: kLaser = 0)
static void test_gain_meaning() {
  auto setup = [](Sim& s, double p, double i) {
    s.kLaser = 0;
    s.lk.s.p1 = p; s.lk.s.i1 = i;
    s.lk.s.ngood = 1;
    s.run(3);   // locked at err = 0
  };
  {   // proportional: output = p1 * err, and follows the error back
    Sim s; setup(s, 0.1, 0);
    const double fb0 = s.lk.feedback;
    s.run(5, [&](int i) { if (i == 0) s.sep0 += 0.5; });
    CHECK(std::fabs(s.lk.feedback - fb0 - 0.05) < 5e-4, "p1: dfb %.5f, expected 0.05", s.lk.feedback - fb0);
    s.run(5, [&](int i) { if (i == 0) s.sep0 -= 0.5; });
    CHECK(std::fabs(s.lk.feedback - fb0) < 5e-4, "p1: output did not return (%.5f)", s.lk.feedback - fb0);
  }
  {   // integral: output ramps by i1 * err each sweep
    Sim s; setup(s, 0, 0.01);
    const double fb0 = s.lk.feedback;
    s.run(5, [&](int i) { if (i == 0) s.sep0 += 0.5; });
    CHECK(std::fabs(s.lk.feedback - fb0 - 5 * 0.005) < 1e-3, "i1: dfb %.5f, expected 0.025",
          s.lk.feedback - fb0);
  }
  {   // g1 scales both terms
    Sim s; setup(s, 0.1, 0.01);
    s.lk.s.g1 = 2;
    const double fb0 = s.lk.feedback;
    s.run(1, [&](int) { s.sep0 += 0.5; });
    CHECK(std::fabs(s.lk.feedback - fb0 - 2 * (0.05 + 0.005)) < 1e-3, "g1: dfb %.5f, expected 0.11",
          s.lk.feedback - fb0);
  }
}

// the integral cannot wind up past the rail: after a long push it comes off
// the rail as soon as the error reverses
static void test_no_windup() {
  Sim s;
  s.kLaser = 0;
  s.lk.s.i1 = -0.1;
  s.lk.s.win = 5;
  s.lk.s.ngood = 1;
  s.run(3);
  s.run(200, [&](int i) { if (i == 0) s.sep0 += 0.5; });   // pushes to -rail
  CHECK(s.lk.feedback == -s.lk.s.rail && s.lk.integral == -s.lk.s.rail, "fb %.3f integ %.3f",
        s.lk.feedback, s.lk.integral);
  s.run(1, [&](int) { s.sep0 -= 1.0; });                   // error reverses
  CHECK(s.lk.feedback > -s.lk.s.rail, "still at the rail after the error reversed (%.3f)", s.lk.feedback);
}

// each rejected sweep is counted once, under its reason
static void test_bad_reasons() {
  {   // no peaks: vth above everything
    Sim s; s.lk.s.vth = 20.0; s.run(10);
    CHECK(s.lk.nBad == s.lk.nBadNone && s.lk.nBadNone >= 8 && s.lk.nBadOne == 0 && s.lk.nBadWin == 0,
          "none: bad %u none %u one %u win %u", s.lk.nBad, s.lk.nBadNone, s.lk.nBadOne, s.lk.nBadWin);
  }
  {   // first peak only: no later peak is at least tmin after the first
    Sim s; s.lk.s.tmin = 38.0; s.run(10);
    CHECK(s.lk.nBad == s.lk.nBadOne && s.lk.nBadOne >= 8 && s.lk.nBadNone == 0 && s.lk.nBadWin == 0,
          "one: bad %u none %u one %u win %u", s.lk.nBad, s.lk.nBadNone, s.lk.nBadOne, s.lk.nBadWin);
  }
  {   // pair found, outside win
    Sim s; s.sep0 = 13.0; s.run(10);
    CHECK(s.lk.nBad == s.lk.nBadWin && s.lk.nBadWin >= 8 && s.lk.nBadNone == 0 && s.lk.nBadOne == 0,
          "win: bad %u none %u one %u win %u", s.lk.nBad, s.lk.nBadNone, s.lk.nBadOne, s.lk.nBadWin);
  }
  {   // lock off counts nothing
    Sim s; s.lk.s.lock = 0; s.sep0 = 13.0; s.run(10);
    CHECK(s.lk.nBad == 0, "off: bad %u", s.lk.nBad);
  }
}

int main() {
  test_centroid_accuracy();
  test_noise_and_height();
  test_lock_converges();
  test_dropout_holds_and_relocks();
  test_single_glitch();
  test_rail_clamps();
  test_lock_switch();
  test_micros_wrap();
  test_gain_meaning();
  test_no_windup();
  test_bad_reasons();
  std::printf(failures ? "%d FAILED\n" : "all passed\n", failures);
  return failures ? 1 : 0;
}
