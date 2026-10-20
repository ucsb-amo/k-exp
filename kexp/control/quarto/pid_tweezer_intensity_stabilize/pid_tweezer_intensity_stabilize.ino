#include "qCommand.h"
qCommand qC;

float SETPOINT1 = 0.0;
float SETPOINT2 = 0.0;
float P1 = -0.01;
float I1 = -0.001;
float P2 = -0.05;
float I2 = -0.005;

double integral1 = 0;
double integral2 = 0;

double v_max_ao_efficiency = 4.;

bool integrator_go1 = true;
bool pid_enable2 = false;

struct Cal
{
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16];
};

void setup() {
  Serial.begin(115200);
  configureADC(1,1,0,BIPOLAR_10V,getMeas1);
  configureADC(2,1,0,BIPOLAR_10V,getSet1);
  configureADC(3,1,0,BIPOLAR_10V,getMeas2);
  configureADC(4,1,0,BIPOLAR_10V,getSet2);

  qC.assignVariable("p1",&P1);
  qC.assignVariable("i1",&I1);

  qC.assignVariable("p2",&P2);
  qC.assignVariable("i2",&I2);
  qC.assignVariable("i2",&I2);

  qC.assignVariable("vmax",&v_max_ao_efficiency);

  enableInterruptTrigger(1,BOTH_EDGES,&hold1);
  enableInterruptTrigger(2,BOTH_EDGES,&hold2);

  qC.addCommand("c",clear_integrator);
  qC.addCommand("ping",ping);

}

void clear_integrator(qCommand& qC, Stream& S) {
  integral1 = 0;
  integral2 = 0;
}

void ping(qCommand& qC, Stream& S)
{
  struct Cal cal2;
  readNVMblock(&cal2, sizeof(cal2), 0xFA00);
  Serial.println(cal2.cal_d);
}

void hold1() {
  if (triggerRead(1)) {
    integral1 = 0;
    integrator_go1 = false;
  } else {
    integrator_go1 = true;
  }
}

void hold2() {
  if (triggerRead(2)) {
    pid_enable2 = true;
    integral2 = v_max_ao_efficiency;
  } else {
    pid_enable2 = false;
    integral2 = 0;
  }
}

//Read ADC1 (PD 1), output it at DAC3, calculate PID, output PID at DAC1
void getMeas1() {
  double newadc1 = readADC1_from_ISR();

  // monitoring output: PD 1 voltage as read in
  writeDAC(3, handle_monitor_overflow(newadc1));

  double prop1 = (newadc1-SETPOINT1) * P1;
  if (integrator_go1) {
    integral1 += (newadc1-SETPOINT1) * I1;
    integral1 = handle_overflow(integral1);
  }
  double newdac1 = prop1 + integral1;

  ///Bit overflow check conditions
  newdac1 = handle_overflow(newdac1);
  writeDAC(1,newdac1);
}

void getSet1(){
  SETPOINT1 = readADC2_from_ISR();
}

//Read ADC3 (PD 2), output it at DAC4, calculate PID, output PID at DAC2
void getMeas2() {
  double newadc2 = readADC3_from_ISR();
  double newdac2 = 0.;

  // monitoring output: PD 2 voltage as read in
  writeDAC(4, handle_monitor_overflow(newadc2));

  if (pid_enable2) {
    double prop2 = (newadc2-SETPOINT2) * P2;
    integral2 += (newadc2-SETPOINT2) * I2;
    integral2 = handle_overflow(integral2);
    newdac2 = prop2 + integral2;}
  else {
    newdac2 = v_max_ao_efficiency;
  }

  ///Bit overflow check conditions
  newdac2 = handle_overflow(newdac2);
  writeDAC(2,newdac2);
}

void getSet2(){
  SETPOINT2 = readADC4_from_ISR();
}

// Keep a control output in the AO driver's 0-10 V range (and below the DAC rail, so it cannot wrap)
double handle_overflow(double num) {
  if (num > 10) {
    num = 9.99;
  } else if (num < 0) {
    num = 0.;
  } else {
  }
  return num;
}

// Monitor outputs pass the reading through unchanged (negative included); only a reading at the
// +/-10 V rail is pulled in to +/-9.99 V so it cannot wrap on the DAC
double handle_monitor_overflow(double num) {
  if (num > 9.99) {
    num = 9.99;
  } else if (num < -9.99) {
    num = -9.99;
  } else {
  }
  return num;
}

void loop() {
  qC.readSerial(Serial);
}
