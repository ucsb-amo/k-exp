#include "qCommand.h"
qCommand qC;
IntervalTimer DAC_Timer; 
IntervalTimer plot;

double currentSignalValue = 0;


double Vth = 0.8; //voltage thresold for identifying the peaks
double G1 = 1; // switich of feedback
double P1 = 0.0; // p gain for feedback, typically setting it as 0.001
double I1 = 0.0; // i gain, but it is not quite nessary and setting zero is OK for most cases
double D1 = 0.0; // same case to i gain
double setpoint1 = 10; // separation of the peaks we want
double newadc1 = 0;

double  firstPeakTime = 0;
double  secondPeakTime = 0;
bool firstPeakDetected = false;
double startTime = 0;
double  peakSeparation = 0;

unsigned long lastRisingEdgeTime = 0;
unsigned long currentRisingEdgeTime = 0;
unsigned long period = 0;
int lastState = LOW;
double feedback = 0;
double er = 0;
double i_er = 0;
double d_er = 0;
int s = 0;

void setup() {
  configureADC(1,1,0,BIPOLAR_10V,getADC1);

  qC.assignVariable("setp",&setpoint1);
  qC.assignVariable("vth",&Vth);
  qC.assignVariable("g1",&G1);
  qC.assignVariable("p1",&P1);  
  qC.assignVariable("i1",&I1);
  qC.assignVariable("d1",&D1);
  qC.assignVariable("serial",&s);
  enableInterruptTrigger(1,BOTH_EDGES,&hold1);
}

void hold1() {
  if (triggerRead(1)) {
    plot.begin(update, 1e1);
  } else {
  }
}

void getADC1(void) {
  double newadc1 = readADC1_from_ISR(); //read ADC voltage
  currentSignalValue = newadc1;
}

void update(void) {
  static double previousSignalValue = 0;
  static double secondPreviousSignalValue = 0;  
  double currentTime = micros()/1000.000;
  
  int TriggerState = triggerRead(1);
  // searching peaks during a trigger period
  if (lastState == LOW && TriggerState == HIGH) {
    currentRisingEdgeTime = currentTime;
    if (lastRisingEdgeTime != 0) {
      period = currentRisingEdgeTime - lastRisingEdgeTime;
    }
    lastRisingEdgeTime = currentRisingEdgeTime;
    if (currentTime - startTime >= period) {
      startTime = currentTime;
      firstPeakDetected = false;
      firstPeakTime = 0;
      secondPeakTime = 0;
    }
  }

  lastState = TriggerState;
  // identifying the first and second peaks
  if (previousSignalValue > currentSignalValue && previousSignalValue > secondPreviousSignalValue && previousSignalValue > Vth) {
    // static unsigned long lastr = 0; 
    if (!firstPeakDetected) {
      firstPeakTime = currentTime;
      firstPeakDetected = true;      
      // delay(2);
    } 
    // identifying the first and second peaks
    else if (currentTime - firstPeakTime > 2 && firstPeakDetected && secondPeakTime == 0) {

      secondPeakTime = currentTime;
      peakSeparation = secondPeakTime - firstPeakTime;
      // calculate the current distance between two peaks
      // and the difference between current distance and setting distance
      if (feedback < -0.8 && feedback > 0.8) { 
        feedback = 0;
      } else { 
        i_er = peakSeparation-setpoint1 + er;
        d_er = peakSeparation-setpoint1 - er;
        er = peakSeparation-setpoint1;
        feedback = (feedback + er * P1 + i_er * I1 + d_er * D1) * G1;  
      }
      writeDAC(1, feedback);
    }  
  }
  secondPreviousSignalValue = previousSignalValue;
  previousSignalValue = currentSignalValue;
}

void loop() {
  qC.readSerial(Serial);  
  if (s == 1){
  static unsigned long lastrun = 0;    
	if (millis() > lastrun) { 
    	lastrun = millis() + 10*period;
	    toggleLEDGreen();
      Serial.println(peakSeparation, 3);         //Serial.println(", ");
        //  Serial.print(feedback, 4);         Serial.print(", ");
        //  Serial.print(setpoint1, 4);          Serial.print(", ");
        //  Serial.println(period, 4);
	}
  }
}