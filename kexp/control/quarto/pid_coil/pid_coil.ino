#include "qCommand.h"
qCommand qC;

// Dual-regime coil PID.
//
// Merges pid_coil_old (low-current gains + gain switching on |Vgs|) and
// pid_coil (high-current gains + gain switching on |error|). The regime is
// selected from the DC current monitor (inputA):
//
//   inputA <  V_regime  ->  low-current regime  (behaves like pid_coil_old)
//   inputA >= V_regime  ->  high-current regime (behaves like pid_coil)
//
// Each regime carries its own pair of gain sets (set 0 / set 1) and its own
// criterion for switching between them, since the two originals used
// different criteria:
//
//   low-current : |newdac1| <  Vgs_threshold0       -> set 0, else set 1
//   high-current: |error|   >  gain_change_threshold -> set 0, else set 1

struct Cal
{
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16];
};

IntervalTimer plot;
double inputA = 0;
double inputB = 0;
double inputT = 0;
double outputA = 0;
double outputB = 0;

double newdac1 = 0.;

float SETPOINT1 = 0.0;

bool blockPID = false;
double v_manual = 6.;

// Regime selection threshold on inputA (DC current monitor, V)
float V_regime = 2.5;

// ---- low-current regime gains (from pid_coil_old) ----
float P10L = 100;
float I10L = 0.05;
float P11L = 300;
float I11L = 20;
// low-current gain switching: on gate voltage magnitude
float Vgs_threshold0 = 5.2;

// ---- high-current regime gains (from pid_coil, updated 2026-03-17) ----
float P10H = 5.0;
float I10H = 0.006;
float P11H = 2.;
float I11H = 0.5;
// high-current gain switching: on error magnitude
float gain_change_threshold = 0.002;

// active gains
float P1 = 0;
float I1 = 0;
float D1 = 0;

// which regime / gain set is active (for monitoring only)
volatile int regime1 = 0;   // 0 = low-current, 1 = high-current
volatile int gainset1 = 0;  // 0 = set 0 (P10/I10), 1 = set 1 (P11/I11)

// How much the AC coupled signal is added
// Better description: multiplies the amplified AC signal to reduce it to original scale (since was preamplified by SRS560)
//float CH2F2 = 0.05;
float CH2F = (2/3)*0.05;

double integral1 = 0.;
double integral2 = 0.;

bool pid_enable1 = false;
bool pid_enable2 = false;

volatile bool enable_print = false;
volatile bool manual_override1 = false;

void setup()
{
  configureADC(1,1,0,BIPOLAR_10V,getMeas1);
  configureADC(3,1,0,BIPOLAR_10V,getSet1);
  configureADC(2,1,0,BIPOLAR_10V,getMeas2);

  // regime threshold
  qC.assignVariable("vr",&V_regime);

  // low-current regime
  qC.assignVariable("p10l",&P10L);
  qC.assignVariable("i10l",&I10L);
  qC.assignVariable("p11l",&P11L);
  qC.assignVariable("i11l",&I11L);
  qC.assignVariable("v0",&Vgs_threshold0);

  // high-current regime
  qC.assignVariable("p10h",&P10H);
  qC.assignVariable("i10h",&I10H);
  qC.assignVariable("p11h",&P11H);
  qC.assignVariable("i11h",&I11H);
  qC.assignVariable("g0",&gain_change_threshold);

  qC.assignVariable("id1",&D1);

  qC.assignVariable("ch2",&CH2F);

  qC.assignVariable("v",&v_manual);

  enableInterruptTrigger(1,BOTH_EDGES,&switch1);

  qC.addCommand("s", togglePrint);
  qC.addCommand("c",clear_integrator);
  qC.addCommand("m", toggleManual);
  qC.addCommand("on",switch_on);
  qC.addCommand("off",switch_off);
  qC.addCommand("ping",ping);

  // start in the low-current regime, gain set 0
  P1 = P10L;
  I1 = I10L;
}

void togglePrint(qCommand& qC, Stream& S) { enable_print = !enable_print; }
void toggleManual(qCommand& qC, Stream& S) { manual_override1 = !manual_override1; }

void switch_on(qCommand& qC, Stream& S)
{
  pid_enable1 = true;
  integral1 = 0.;
}

void switch_off(qCommand& qC, Stream& S)
{
  pid_enable1 = false;
  integral1 = 0.;
}

void ping(qCommand& qC, Stream& S)
{
  struct Cal cal2;
  readNVMblock(&cal2, sizeof(cal2), 0xFA00);
  Serial.println(cal2.cal_d);
}

//At TTL edges, check value of TTL, clear integrator, and then enable/disable PID depending on value
void switch1()
{
  if (triggerRead(1)) {
    pid_enable1 = true;
  } else {
    pid_enable1 = false;
  }
  integral1 = 0.;
}

void clear_integrator(qCommand& qC, Stream& S)
{
  integral1 = 0;
  integral2 = 0;
}

//Read ADC, output ADC value at Ch3 & 4 calculate PID, output PID at CH1, 2
void getMeas1()
{
  static double prevA = 0;
  double newadc1 = readADC1_from_ISR();
  inputA = newadc1;
  writeDAC(4,inputA);//Ch2 on oscope, as of 7/30/25
  writeDAC(1, inputB);//Ch3 on oscope, as of 7/30/25

  inputT = inputA + inputB*CH2F; // I believe we should remove the (1-CH2F) term from the DC part -- fixes observed offset in stabilized current from expected value
  double error = inputT-SETPOINT1;
  if (pid_enable1 && !blockPID)
  {
    double prop1 = error * P1;
    integral1 += (error) * I1;
    double derivT = (inputT - prevA) * D1;
    newdac1 = prop1 + integral1 + derivT;
  }
  else
  {
    newdac1 = 0.;
  }

  //Bit overflow check conditions
  if(newdac1>10)
  {
    newdac1 = 9.9;
  }
  else if(newdac1<-10)
  {
    newdac1 = -9.9;
  }
  else {}

  if(manual_override1){
    newdac1 = v_manual;
  }

  writeDAC(3, newdac1);//To the FET
  prevA = inputT;

  //gain scheduling
  // 1) pick the regime from the DC current monitor
  // 2) pick the gain set within that regime using that regime's own criterion
  if (inputA < V_regime)
  {
    // low-current regime (pid_coil_old): switch on gate voltage magnitude
    regime1 = 0;
    if (abs(newdac1) < Vgs_threshold0)
    {
      gainset1 = 0;
      P1 = P10L;
      I1 = I10L;
    }
    else
    {
      gainset1 = 1;
      P1 = P11L;
      I1 = I11L;
    }
  }
  else
  {
    // high-current regime (pid_coil): switch on error magnitude
    regime1 = 1;
    if (abs(error) > gain_change_threshold)
    {
      gainset1 = 0;
      P1 = P10H;
      I1 = I10H;
    }
    else
    {
      gainset1 = 1;
      P1 = P11H;
      I1 = I11H;
    }
  }

}

void getSet1()
{
  SETPOINT1 = readADC3_from_ISR();
}

void getMeas2()
 {
  double newadc2 = readADC2_from_ISR();
  inputB = newadc2;
}

void loop()
{
  qC.readSerial(Serial);

  static uint32_t last_ms = 0;
  if (!enable_print || (millis() - last_ms < 100)) return;
  last_ms = millis();

  Serial.print(SETPOINT1, 4);
  Serial.println(" ");
  Serial.print(inputA, 4);
  Serial.println(" ");
  Serial.print(inputA*40);
  Serial.println();
  Serial.print(newdac1, 4);
  Serial.println(" ");
  Serial.print("regime ");
  Serial.print(regime1);
  Serial.print(" set ");
  Serial.println(gainset1);
}
