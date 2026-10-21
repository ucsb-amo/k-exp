// Tweezer intensity stabilization with a LOGARITHMIC photodiode (one PI loop).
// Written for the Koheron PDX10R (log(A) output: 300 mV/decade nominal, 100 pA intercept, 1 kOhm output
// impedance; datasheet). At 1064 nm use the InGaAs version (PDX10R-D-INGAAS, 900-1700 nm); the Si version
// is specified to 1000 nm only.
//
// Wiring
//   ADC1       log-PD output (V = vref + klog * log10(P / P_ref)), read on the +/-2.5 V range
//              (PD_ADC_RANGE): 76 uV per LSB = 0.06 % of power at 0.3 V/decade, vs 0.23 % on +/-10 V.
//              The PD output must stay below 2.5 V (nominal 2.5 V = 32 mA of photocurrent, far above its
//              rated input) -- check the measured window before changing the range.
//   ADC2       setpoint from ARTIQ (meaning set by smode, below)
//   Trigger 1  HIGH = loop off: AO output 0 V, integrator cleared
//   DAC1       AO driver control, clamped to [0, 9.99] V
//   DAC3       monitor: log-PD reading as read in
//   DAC4       monitor: the target log-PD voltage the loop is holding (-9.99 V = no valid target, loop off)
//
// Setpoint modes (serial "smode")
//   0  setpoint is an affine map of the target log-PD voltage: target = soffset + sgain * setpoint.
//      The host converts power -> setpoint (kexp.calibrations.tweezer_logpd.power_to_log_setpoint); the
//      calibration lives in git and in the run params. sgain < 1 spreads the PD's narrow window (about
//      0.7 V for 2.4 decades) over the ARTIQ DAC's range: finer setpoint steps, less setpoint-cable noise.
//      Choose soffset below vset_min so that a 0 V setpoint is off (the host checks this).
//   1  setpoint is LINEAR in power. The firmware converts it once per sample:
//      target = vref + klog * log10(setpoint / sref). The calibration lives here; read it back with "cal"
//      and record it with the run, or the meaning of a setpoint volt is not reconstructable.
//
// In both modes the PI loop compares the log-PD reading with the target, so the error is
// klog * log10(P / P_target): a fractional error, the same at every power.
//
// Floor protection: the log PD flattens near its dark/stray-light floor, where the loop has no gain and the
// integrator would run to the rail (full power when light returns). The loop only runs while
// target >= vset_min (turn-on needs vset_min + hyst). A NaN calibration constant never passes, so an
// uncalibrated board keeps the AO at 0 V. A setpoint of 0 V in mode 1 is "off" (log10 of 0).
// In mode 0, "off" is the TTL or a setpoint below vset_min -- if the log PD's floor is negative,
// a 0 V setpoint is NOT off.
//
// Gain signs follow the linear tweezer firmware: negative P/I raise the AO output when the PD reads low.
// The floor switch assumes the log-PD voltage RISES with power (klog > 0); a module with an inverted
// output needs an inverting stage in front of ADC1, not just flipped gains.
//
// Serial commands: p, i, smode, sgain, soffset, klog, vref, sref, vset_min, vsat, hyst, preload (read/set);
//   cal (print calibration, key=value lines), s (status), t (max ISR times, then reset), c (clear integrator), ping.
//
// NOT compiled or run on hardware as of 2026-10-21.

#include "qCommand.h"
#include <math.h>
qCommand qC;

const char *FW_VERSION = "tweezer_logpd v2 2026-10-21";

const adc_scale_t PD_ADC_RANGE = BIPOLAR_2500mV;

float P1 = -0.05;
float I1 = -0.005;

int smode = 0;
double sgain = 1.;      // smode 0: target = soffset + sgain * setpoint
double soffset = 0.;

// Calibration (NaN = not calibrated: the loop stays off)
double klog = NAN;      // log-PD V per decade of power
double vref = NAN;      // log-PD V at the reference power
double sref = NAN;      // mode 1: setpoint V meaning the reference power
double vset_min = NAN;  // lowest allowed target: measured floor + margin
double vsat = NAN;      // log-PD V where its output compresses (counted, not enforced)
double hyst = 0.01;     // V of hysteresis on the floor switch
double preload = 0.;    // integrator value when the loop turns on

volatile double target = NAN;
volatile bool setpoint_ok = false;
volatile bool ttl_off = true;
volatile bool was_running = false;
volatile bool was_sat = false;
volatile bool was_rail = false;
volatile double integral = 0.;
volatile double last_out = 0.;
volatile double last_meas = 0.;

volatile uint32_t n_sat = 0;   // times the target entered the compression region
volatile uint32_t n_rail = 0;  // times the PI output hit a clamp
volatile uint32_t cyc_set_max = 0;
volatile uint32_t cyc_meas_max = 0;

struct Cal
{
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16];
};

void setup() {
  Serial.begin(115200);
  ttl_off = triggerRead(1);
  configureADC(1,1,0,PD_ADC_RANGE,getMeas);
  configureADC(2,1,0,BIPOLAR_10V,getSet);

  qC.assignVariable("p",&P1);
  qC.assignVariable("i",&I1);
  qC.assignVariable("smode",&smode);
  qC.assignVariable("sgain",&sgain);
  qC.assignVariable("soffset",&soffset);
  qC.assignVariable("klog",&klog);
  qC.assignVariable("vref",&vref);
  qC.assignVariable("sref",&sref);
  qC.assignVariable("vset_min",&vset_min);
  qC.assignVariable("vsat",&vsat);
  qC.assignVariable("hyst",&hyst);
  qC.assignVariable("preload",&preload);

  enableInterruptTrigger(1,BOTH_EDGES,&hold1);

  qC.addCommand("c",clear_integrator);
  qC.addCommand("ping",ping);
  qC.addCommand("cal",print_cal);
  qC.addCommand("s",print_status);
  qC.addCommand("t",print_timing);
}

void clear_integrator(qCommand& qC, Stream& S) {
  integral = 0;
}

void ping(qCommand& qC, Stream& S) {
  struct Cal cal2;
  readNVMblock(&cal2, sizeof(cal2), 0xFA00);
  Serial.println(cal2.cal_d);
}

// Everything that sets what a setpoint volt means, as key=value lines, then "end"
void print_cal(qCommand& qC, Stream& S) {
  S.printf("fw=%s\n", FW_VERSION);
  S.printf("smode=%d\n", smode);
  S.printf("pd_adc_range=%d\n", (int)PD_ADC_RANGE);
  S.printf("sgain=%.9g\n", sgain);
  S.printf("soffset=%.9g\n", soffset);
  S.printf("klog=%.9g\n", klog);
  S.printf("vref=%.9g\n", vref);
  S.printf("sref=%.9g\n", sref);
  S.printf("vset_min=%.9g\n", vset_min);
  S.printf("vsat=%.9g\n", vsat);
  S.printf("hyst=%.9g\n", hyst);
  S.printf("preload=%.9g\n", preload);
  S.printf("p=%.9g\n", P1);
  S.printf("i=%.9g\n", I1);
  S.printf("end\n");
}

void print_status(qCommand& qC, Stream& S) {
  S.printf("target=%.6g ok=%d ttl_off=%d running=%d\n", target, setpoint_ok, ttl_off, was_running);
  S.printf("meas=%.6g out=%.6g integral=%.6g\n", last_meas, last_out, integral);
  S.printf("n_sat=%lu n_rail=%lu\n", (unsigned long)n_sat, (unsigned long)n_rail);
}

void print_timing(qCommand& qC, Stream& S) {
  double us_per_cyc = 1e6 / (double)F_CPU_ACTUAL;
  S.printf("set_isr_max_us=%.4g meas_isr_max_us=%.4g (sample period 1 us each)\n",
           cyc_set_max * us_per_cyc, cyc_meas_max * us_per_cyc);
  cyc_set_max = 0;
  cyc_meas_max = 0;
}

void hold1() {
  ttl_off = triggerRead(1);
  if (ttl_off) {
    integral = 0;
  }
}

// Read the setpoint, convert it to the target log-PD voltage, decide whether the loop may run
void getSet() {
  uint32_t c0 = ARM_DWT_CYCCNT;
  double s = readADC2_from_ISR();
  double t;
  if (smode == 1) {
    t = (s > 0.) ? vref + klog * log10(s / sref) : NAN;
  } else {
    t = soffset + sgain * s;
  }
  // NaN compares false: an uncalibrated constant or a non-positive mode-1 setpoint never passes
  bool ok = setpoint_ok ? (t >= vset_min) : (t >= vset_min + hyst);
  bool sat = (t >= vsat);
  if (sat && !was_sat) n_sat++;
  was_sat = sat;
  target = t;
  setpoint_ok = ok;
  writeDAC(4, isnan(t) ? -9.99 : handle_monitor_overflow(t));
  uint32_t dc = ARM_DWT_CYCCNT - c0;
  if (dc > cyc_set_max) cyc_set_max = dc;
}

// Read the log PD, run the PI loop on the log-domain error, write the AO control voltage
void getMeas() {
  uint32_t c0 = ARM_DWT_CYCCNT;
  double v = readADC1_from_ISR();
  writeDAC(3, handle_monitor_overflow(v));
  last_meas = v;

  bool run = setpoint_ok && !ttl_off;
  double out = 0.;
  if (run) {
    if (!was_running) integral = preload;
    double err = v - target;                       // = klog * log10(P / P_target)
    integral = handle_overflow(integral + err * I1);
    out = err * P1 + integral;
    bool rail = (out > 9.99) || (out < 0.);
    if (rail && !was_rail) n_rail++;
    was_rail = rail;
    out = handle_overflow(out);
  } else {
    integral = 0;
    was_rail = false;
  }
  was_running = run;
  last_out = out;
  writeDAC(1, out);
  uint32_t dc = ARM_DWT_CYCCNT - c0;
  if (dc > cyc_meas_max) cyc_meas_max = dc;
}

// Keep a control output in the AO driver's 0-10 V range (and below the DAC rail, so it cannot wrap)
double handle_overflow(double num) {
  if (num > 9.99) {
    num = 9.99;
  } else if (num < 0) {
    num = 0.;
  }
  return num;
}

// Monitor outputs pass the reading through; only a reading at the +/-10 V rail is pulled in to +/-9.99 V
double handle_monitor_overflow(double num) {
  if (num > 9.99) {
    num = 9.99;
  } else if (num < -9.99) {
    num = -9.99;
  }
  return num;
}

void loop() {
  qC.readSerial(Serial);
}
