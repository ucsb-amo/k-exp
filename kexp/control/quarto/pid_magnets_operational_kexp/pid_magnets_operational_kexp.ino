#include "qCommand.h"
qCommand qC;

IntervalTimer plot;
double inputA = 0;
double inputB = 0;
double outputA = 0;
double outputB = 0;


float SETPOINT1 = 0.0;
float SETPOINT2 = 0.0;
float P1 = 50;
float I1 = 0.007;
float P2 = 50;
float I2 = 0.007;

double integral1 = 0.;
double integral2 = 0.;


//offset is the output voltage when I and P are both 0
float offset = 3.1;
//Time between each serial output
double uTime = 1e2;

bool pid_enable1 = false;
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
  qC.assignVariable("o",&offset);
  qC.assignVariable("u",&uTime);
  // qC.assignVariable("vmax",&v_max_ao_efficiency);

  enableInterruptTrigger(1,BOTH_EDGES,&switch1);
  enableInterruptTrigger(2,BOTH_EDGES,&switch2);

  qC.addCommand("c",clear_integrator);
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

void update(void) 
{

}


void clear_integrator(qCommand& qC, Stream& S) {
  integral1 = 0;
  integral2 = 0;
}

//Read ADC, output ADC value at Ch3 & 4 calculate PID, output PID at CH1, 2 
void getMeas1() {
  double newadc1 = readADC1_from_ISR();
  inputA = newadc1;
  writeDAC(3,newadc1);
  //writeDAC(3, inputA);
  double newdac1 = 0.;
  if (pid_enable1) {
    double prop1 = (newadc1-SETPOINT1) * P1;
    integral1 += (newadc1-SETPOINT1) * I1;
    newdac1 = prop1 + integral1;}
  else {
    newdac1 = 0.;
  }
  outputA = newadc1;
  ///Bit overflow check conditions
  if(newdac1>10)
  {
    newdac1 = 9.9;
    writeDAC(1,9.9);
  }
  else if(newdac1<-10)
  {
    newdac1 = -9.9;
    writeDAC(1,-9.9);
  }
  else
  {
    writeDAC(1,newdac1+offset);
  }
  
}

void getSet1(){
  SETPOINT1 = readADC2_from_ISR();
}

void getMeas2() {
  double newadc2 = readADC3_from_ISR();
  inputB = newadc2;
  writeDAC(4, inputB);
  double newdac2 = 0.;
  if (pid_enable2) {
    double prop2 = (newadc2-SETPOINT2) * P2;
    integral2 += (newadc2-SETPOINT2) * I2;
    newdac2 = prop2 + integral2;}

  else {
    newdac2 = 0.;
  }

  ///Bit overflow check conditions
  if(newdac2>10)
  {
    newdac2 = 9.9;
    writeDAC(2,9.9);
  }
  else if(newdac2<-10)
  {
    newdac2 = -9.9;
    writeDAC(2,-9.9);
  }
  else
  {
    writeDAC(2,newdac2+offset);
  }
  //writeDAC(4,newdac2+offset);
}

void getSet2(){
  SETPOINT2 = readADC4_from_ISR();
}

void loop() {
  qC.readSerial(Serial);
}