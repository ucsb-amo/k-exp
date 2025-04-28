#include "qCommand.h"
qCommand qC;
IntervalTimer DAC_Timer; 

float SETPOINT1 = 0.23*1000*0.8; // 0.8 TTL period
float P1 = 1;
float I1 = 0;

double integral1 = 0;

double v_max_ao_efficiency = 4.;

bool integrator_go1 = true;

double V_now = 0;
double V_past = 0;
double V2_past = 0;
float dV = 0;
float Vth = 1;
double newadc1 = 0;

bool peakDetected = false;
unsigned long t0;
unsigned long t1;
unsigned long firstPeakTime = 0;
unsigned long lastPeaktime = 0;
unsigned long secondPeakTime = 0;
bool firstPeakFound = false;
bool secondPeakFound = false;

unsigned long peakSeparation = 0;
float freq = 0;

void setup() {
  configureADC(1,1,0,BIPOLAR_10V,getMeas1);
  // configureADC(2,1,0,BIPOLAR_10V,getSet1);

  qC.assignVariable("p1",&P1);
  qC.assignVariable("i1",&I1);
  qC.assignVariable("vth",&Vth);
  // qC.assignVariable("vmax",&v_max_ao_efficiency);

  enableInterruptTrigger(1,BOTH_EDGES,&hold1);
  freq = readTriggerClockFreq();

  qC.addCommand("c",clear_integrator);
  // t0 = millis();
}

void clear_integrator(qCommand& qC, Stream& S) {
  integral1 = 0;
}

void hold1() {
  if (triggerRead(1)) {
    integral1 = 0;
    integrator_go1 = false;
  } else {
    integrator_go1 = true;
  }
}

void getMeas1() {
  t0 = millis();
  V_now = readADC1_from_ISR();
  dV = V_now - V_past;
  if (t0 < 121){
    if (dV > Vth){
      firstPeakTime = millis() - t0;
    }
  } else {
    t0 = 0;
  }


  // if (V_past < V_now && V_past < V2_past) {

  //     peakDetected = true;
      
  //     if (!firstPeakFound) {
  //       firstPeakTime = millis();
  //       firstPeakFound = true;
  //     }

  //     else if (!secondPeakFound) {
  //       secondPeakTime = millis();
  //       secondPeakFound = true;      
  //       peakSeparation = secondPeakTime - firstPeakTime;
  //     }
  // }  

  double newadc1 = (dV + I1) * P1;
  writeDAC(1, newadc1);
  // double prop1 = (newadc1 - SETPOINT1) * P1;
  // if (integrator_go1) {
  //   integral1 += (newadc1 - SETPOINT1) * I1;}
  // double newdac1 = prop1 + integral1;
  // writeDAC(1,newdac1);
  V2_past = V_past;
  V_past = V_now;
}


// void getSet1(){
//   SETPOINT1 = readADC2_from_ISR();
// }

void loop() {
  qC.readSerial(Serial);
  // t0 = millis();
  V_now = readADC1_from_ISR();
  dV = (V_now - V_past);
  
    if (dV > Vth){
      t1 = millis();
      lastPeaktime = firstPeakTime;
      firstPeakTime = t1 - t0;
      double d = firstPeakTime - lastPeaktime;
      if (d > 15*freq) { firstPeakTime = lastPeaktime; }
      Serial.print("t1-t0: ");
      Serial.print(t1-t0);
      t0 = t1;
      newadc1 = (firstPeakTime + I1) * P1;
      Serial.print("; inside output1: ");      Serial.print(firstPeakTime);  
      Serial.print("; inside output2: ");      Serial.print(lastPeaktime);        
      Serial.print("; inside output3: ");      Serial.print(firstPeakTime - lastPeaktime);  
      Serial.print("; trigger freq: ");      Serial.print(freq);
      Serial.print("; V_now: ");      Serial.print(V_now);
      Serial.print("; dV: ");      Serial.print(dV);
      Serial.print("; output: ");      Serial.println(newadc1);
    }



  // if (V_past < V_now && V_past < V2_past) {

  //     peakDetected = true;
      
  //     if (!firstPeakFound) {
  //       firstPeakTime = millis();
  //       firstPeakFound = true;
  //     }

  //     else if (!secondPeakFound) {
  //       secondPeakTime = millis();
  //       secondPeakFound = true;      
  //       peakSeparation = secondPeakTime - firstPeakTime;
  //     }
  // }  

  // writeDAC(1, newadc1);
  // double prop1 = (newadc1 - SETPOINT1) * P1;
  // if (integrator_go1) {
  //   integral1 += (newadc1 - SETPOINT1) * I1;}
  // double newdac1 = prop1 + integral1;
  // writeDAC(1,newdac1);
  // V2_past = V_past;
  V_past = V_now;
}