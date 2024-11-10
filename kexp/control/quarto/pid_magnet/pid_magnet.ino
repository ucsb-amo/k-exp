#include "qCommand.h"
qCommand qC;

IntervalTimer plot;

float SETPOINT1 = 0.0;
float SETPOINT2 = 0.0;
float P1 = 0.02;
float I1 = 0.01;
float P2 = 0.05;
float I2 = 0.005;

double integral1 = 0.;
double integral2 = 0.;

bool pid_enable1 = true;
bool pid_enable2 = true;

void setup() {
  configureADC(1,1,0,BIPOLAR_10V,getMeas1);
  configureADC(2,1,0,BIPOLAR_10V,getSet1);
  configureADC(3,1,0,BIPOLAR_10V,getMeas2);
  configureADC(4,1,0,BIPOLAR_10V,getSet2);

  qC.assignVariable("p1",&P1);
  qC.assignVariable("i1",&I1);

  qC.assignVariable("p2",&P2);
  qC.assignVariable("i2",&I2);

  // qC.assignVariable("vmax",&v_max_ao_efficiency);

  enableInterruptTrigger(1,BOTH_EDGES,&switch1);
  enableInterruptTrigger(2,BOTH_EDGES,&switch2);

  qC.addCommand("c",clear_integrator);
}

void switch1() {
  if (triggerRead(1)) {
    pid_enable1 = true;
  } else {
    pid_enable1 = false;
  }
  integral1 = 0.;
}

void switch1() {
  if (triggerRead(2)) {
    pid_enable2 = true;
  } else {
    pid_enable2 = false;
  }
  integral2 = 0.;
}

void clear_integrator(qCommand& qC, Stream& S) {
  integral1 = 0;
  integral2 = 0;
}

void getMeas1() {
  double newadc1 = readADC1_from_ISR();
  double newdac1 = 0.;
  if (pid_enable1) {
    double prop1 = (newadc1-SETPOINT1) * P1;
    integral1 += (newadc1-SETPOINT1) * I1;
    newdac1 = prop1 + integral1;}
  else {
    newdac1 = 0.;
  }
  writeDAC(1,newdac1);
}

void getSet1(){
  SETPOINT1 = readADC2_from_ISR();
}

void getMeas2() {
  double newadc2 = readADC3_from_ISR();
  double newdac2 = 0.;
  if (pid_enable2) {
    double prop2 = (newadc2-SETPOINT2) * P2;
    integral2 += (newadc2-SETPOINT2) * I2;
    newdac2 = prop2 + integral2;}
  else {
    newdac2 = 0.;
  }
  writeDAC(2,newdac2);
}

void getSet2(){
  SETPOINT2 = readADC4_from_ISR();
}

void loop() {
  qC.readSerial(Serial);
}