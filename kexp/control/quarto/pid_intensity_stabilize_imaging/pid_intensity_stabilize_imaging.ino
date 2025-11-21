#include "qCommand.h"
qCommand qC;
struct Cal 
{
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16];
};

float SETPOINT1 = 1.;
float P1 = -0.055;
float I1 = -0.005;
double integral1 = 0.;
bool pid_enable1 = true;
bool manual_override1 = false;

void setup() {
  // put your setup code here, to run once:
  Serial.begin(115200);
  qC.addCommand("ping",ping);

  configureADC(1, 1, 0, BIPOLAR_1250mV, pid1);
  configureADC(2, 1, 0, BIPOLAR_1250mV, getSet1);

  qC.assignVariable("p1", &P1);
  qC.assignVariable("i1", &I1);
  qC.assignVariable("set1", &SETPOINT1);

  enableInterruptTrigger(1,BOTH_EDGES,&switch1);
  enableInterruptTrigger(2,BOTH_EDGES,&manualOverride);

  qC.addCommand("c", clear_integrator);
  qC.addCommand("m", toggleManual);
}

void toggleManual(qCommand& qC, Stream& S) {
  manual_override1 = !manual_override1;
}

void manualOverride() {
  if (triggerRead(2)) {
    manual_override1 = true;
  } else {
    manual_override1 = false;
    integral1 = 0;
  }
}

//Read ADC, output ADC value at Ch3 and set point on CH4, calculate PID, output PID at CH1
void pid1() {
  double newadc1 = readADC1_from_ISR();
  double newdac1 = 0.;

  // monitoring outputs
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

  if (manual_override1) {
    newdac1 = 9.9;
  }

  writeDAC(1, newdac1);
}

void getSet1() {
  SETPOINT1 = readADC2_from_ISR();
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

void clear_integrator(qCommand& qC, Stream& S) {
  integral1 = 0;
}

void ping(qCommand& qC, Stream& S) {
  struct Cal cal2;
  readNVMblock(&cal2, sizeof(cal2), 0xFA00);  
  Serial.println(cal2.cal_d); 
}

void loop() {
  // put your main code here, to run repeatedly:
  qC.readSerial(Serial);
}
