#include "qCommand.h"
qCommand qC;

float SETPOINT1 = 9.0;
float SETPOINT2 = 1.5;
float P1 = -.055;
float I1 = -0.006;
float P2 = -0.055;
float I2 = -0.006;

double integral1 = 0.;
double integral2 = 0.;

bool pid_enable1 = true;
bool pid_enable2 = true;

struct Cal 
{
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16];
};

void setup() {
  configureADC(1, 1, 0, BIPOLAR_10V, getMeas1);
  // configureADC(2, 1, 0, BIPOLAR_10V, getSet1);
  configureADC(3, 1, 0, BIPOLAR_2500mV, getMeas2);
  // configureADC(4,1,0,BIPOLAR_10V,getSet2);

  qC.assignVariable("p1", &P1);
  qC.assignVariable("i1", &I1);
  qC.assignVariable("p2", &P2);
  qC.assignVariable("i2", &I2);

  qC.assignVariable("set1", &SETPOINT1);
  qC.assignVariable("set2", &SETPOINT2);

  // enableInterruptTrigger(1,BOTH_EDGES,&switch1);
  // enableInterruptTrigger(2,BOTH_EDGES,&switch2);

  qC.addCommand("c", clear_integrator);

  Serial.begin(115200);
  qC.addCommand("ping",ping);
}
//asks for quarto name
void ping(qCommand& qC, Stream& S)
{
  struct Cal cal2;
  readNVMblock(&cal2, sizeof(cal2), 0xFA00);  
  Serial.println(cal2.cal_d); 
}
//At TTL edges, check value of TTL, clear integrator, and then enable/disable PID depending on value
void switch1() {
  if (triggerRead(1)) {
    pid_enable1 = true;
  } else {
    pid_enable1 = false;
  }
  integral1 = 0.;
}

void switch2() {
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

//Read ADC, output ADC value at Ch3 and set point on CH4, calculate PID, output PID at CH1
void getMeas1() {
  double newadc1 = readADC1_from_ISR();
  double newdac1 = 0.;
  writeDAC(3, newadc1);
  writeDAC(4, SETPOINT1);

  if (pid_enable1) {
    double prop1 = (newadc1 - SETPOINT1) * P1;
    integral1 += (newadc1 - SETPOINT1) * I1;
    newdac1 = prop1 + integral1;
  } else {
    newdac1 = 0.;
  }

  ///Bit overflow check conditions
  if (newdac1 > 10) {
    newdac1 = 9.9;
  } else if (newdac1 < 0) {
    newdac1 = 0.;
  } else {
  }
  writeDAC(1, newdac1);
}

void getSet1() {
  SETPOINT1 = readADC2_from_ISR();
}

void getMeas2() {
  double newadc2 = readADC3_from_ISR();
  double newdac2 = 0.;
  // writeDAC(3, newadc2);
  // writeDAC(4, SETPOINT2);

  if (pid_enable2) {
    double prop2 = (newadc2 - SETPOINT2) * P2;
    integral2 += (newadc2 - SETPOINT2) * I2;
    newdac2 = prop2 + integral2;
  } else {
    newdac2 = 0.;
  }

  ///Bit overflow check conditions
  if (newdac2 > 10) {
    newdac2 = 9.9;
  } else if (newdac2 < 0) {
    newdac2 = 0.;
  } else {
  }
  writeDAC(2, newdac2);
}

void getSet2() {
  // SETPOINT2 = readADC4_from_ISR();
}

void loop() {
  qC.readSerial(Serial);
}