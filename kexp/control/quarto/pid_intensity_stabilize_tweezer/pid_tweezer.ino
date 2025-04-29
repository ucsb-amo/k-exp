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

void setup() {
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
}

void clear_integrator(qCommand& qC, Stream& S) {
  integral1 = 0;
  integral2 = 0;
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

void getMeas1() {
  double newadc1 = readADC1_from_ISR();
  double prop1 = (newadc1-SETPOINT1) * P1;
  if (integrator_go1) {
    integral1 += (newadc1-SETPOINT1) * I1;}
  double newdac1 = prop1 + integral1;
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
    newdac2 = v_max_ao_efficiency;
  }
  writeDAC(2,newdac2);
}

void getSet2(){
  SETPOINT2 = readADC4_from_ISR();
}

void loop() {
  qC.readSerial(Serial);
}