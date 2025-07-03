#include "qCommand.h"
qCommand qC;

IntervalTimer plot;
double inputA = 0;
double inputB = 0;
double inputT = 0;
double outputA = 0;
double outputB = 0;

float SETPOINT1 = 0.0;

///Hard coded gain switching , first number represents inner vs outer, second initial vs long
// float P10 = 3000;
// float I10 = 0.01;
// float P11 = 1000;
// float I11 = 0.150000;
// float P12 = 0;
// float I12 = 4;
// float P1 = 0;
// float I1 = 0;
// float D1 = 0;

// updated 2025/05/20, worse performance than historical?
// yes
// updated 9am 5/21/25
float P10 = 100;
float I10 = 0.05;
float P11 = 100;
float I11 = 10;
float P1 = 0;
float I1 = 0;
float D1 = 0;

// How much the AC coupled signal is added
// Better description: multiplies the amplified AC signal to reduce it to original scale (since was preamplified by SRS560)
//float CH2F2 = 0.05;
float CH2F = (2/3)*0.05;

float Vgs_threshold0 = 5.2;
//float Vgs_threshold1 = 5.7;

double integral1 = 0.;
double integral2 = 0.;

bool pid_enable1 = false;
bool pid_enable2 = false;

void setup() {
  configureADC(1,1,0,BIPOLAR_10V,getMeas1);
  configureADC(3,1,0,BIPOLAR_10V,getSet1);
  configureADC(2,1,0,BIPOLAR_10V,getMeas2);

  qC.assignVariable("p10",&P10);
  qC.assignVariable("i10",&I10);
  qC.assignVariable("p11",&P11);
  qC.assignVariable("i11",&I11);
 // qC.assignVariable("p12",&P12);
 // qC.assignVariable("i12",&I12);
  qC.assignVariable("id1",&D1);

  qC.assignVariable("ch2",&CH2F);

  qC.assignVariable("v0",&Vgs_threshold0);
  //qC.assignVariable("v1",&Vgs_threshold1);

  enableInterruptTrigger(1,BOTH_EDGES,&switch1);

  qC.addCommand("c",clear_integrator);
  qC.addCommand("on",switch_on);
  qC.addCommand("off",switch_off);
  qC.addCommand("name",tell_name);
  P1 = P10;
  I1 = I10;
}

void switch_on()
{
  pid_enable1 = true;
  integral1 = 0.;
}

void switch_off()
{
  pid_enable1 = false;
  integral1 = 0.;
}

void tell_name()
{
  Serial.println("Magnet Stabilization Quarto");
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
  integral2 = 0;
}

//Read ADC, output ADC value at Ch3 & 4 calculate PID, output PID at CH1, 2 
void getMeas1()
{
  static double prevA = 0;
  double newadc1 = readADC1_from_ISR();
  inputA = newadc1;
  writeDAC(4,inputA);
  writeDAC(2, inputB);
  writeDAC(1, inputB);
  // P1 = P11;
  // I1 = I11;
  //}
  double newdac1 = 0.;
  inputT = inputA + inputB*CH2F; // I believe we should remove the (1-CH2F) term from the DC part -- fixes observed offset in stabilized current from expected value
  if (pid_enable1) 
  {
    double prop1 = (inputT-SETPOINT1) * P1;
    integral1 += (inputT-SETPOINT1) * I1;
    double derivT = (inputT - prevA) * D1;
    newdac1 = prop1 + integral1 + derivT;
  }

  else
  {
    newdac1 = 0.;
  }
  outputA = newadc1;

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

  // if(pid_enable1) {newdac1 = 6.;}
  // else {newdac1 = 0.;}
  
  writeDAC(3,newdac1);

  prevA = inputT;
  // if(abs(newdac1)>Vgs_threshold1)
  // {
  //   P1 = P12;
  //   I1 = I12;
  // }
  if (abs(newdac1)<Vgs_threshold0)
  {
    P1 = P10;
    I1 = I10;
  }
  else
  {
    P1 = P11;
    I1 = I11;
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
}