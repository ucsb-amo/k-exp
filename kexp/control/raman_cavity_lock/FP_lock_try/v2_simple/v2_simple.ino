#include "qCommand.h"
qCommand qC;
IntervalTimer DAC_Timer; 
IntervalTimer plot;

double currentSignalValue = 0;
double triggerPeriod = 0;

bool integrator_go1 = true;

float Vth = 0.3;
float P1 = 0.0;
double setpoint1 = 50;

double newadc1 = 0;

double firstPeakTime = 0;
double secondPeakTime = 0;
bool firstPeakDetected = false;
double startTime = 0;
double peakSeparation;

unsigned long lastRisingEdgeTime = 0;
unsigned long currentRisingEdgeTime = 0;
unsigned long period = 0;
int lastState = LOW;
double feedback = 0;

void setup() {
  configureADC(1,1,0,BIPOLAR_10V,getADC1);

  qC.assignVariable("setP",&setpoint1);
  qC.assignVariable("vth",&Vth);
  qC.assignVariable("p1",&P1);

  enableInterruptTrigger(1,BOTH_EDGES,&hold1);
}

void hold1() {
  if (triggerRead(1)) {
    plot.begin(update, 1e1);
  } else {}
}

void getADC1(void) {
  double newadc1 = readADC1_from_ISR(); //read ADC voltage
  currentSignalValue = newadc1;
}

void getTriggerPeriod(void){
  unsigned long highDuration = pulseIn(triggerRead(1), HIGH);
  unsigned long lowDuration = pulseIn(triggerRead(1), LOW);
  triggerPeriod = highDuration + lowDuration;
}

void update(void) {
  static double previousSignalValue = 0;
  static double secondPreviousSignalValue = 0;  
  float currentTime = micros()/1000.000;
  
  int TriggerState = triggerRead(1);

  // calculate the period of trigger
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

  // find peaks and calculate the peaks separation
  if (previousSignalValue > currentSignalValue && previousSignalValue > secondPreviousSignalValue && previousSignalValue > Vth) {
    if (!firstPeakDetected) {
      firstPeakTime = currentTime;
      firstPeakDetected = true;      
      delay(1);
    } 
    else if (firstPeakDetected && secondPeakTime == 0) {
      secondPeakTime = currentTime;
      // Serial.print("Peak1 found at ");
      // Serial.print(firstPeakTime - startTime);
      // Serial.print(" ms; ");

      // Serial.print("Peak2 found at ");
      // Serial.print(secondPeakTime - startTime);
      // Serial.print(" ms; ");

      peakSeparation = secondPeakTime - firstPeakTime;

      if (feedback < -0.9 || feedback > 0.9) { 
        feedback = 0;
      } else { feedback = (feedback/(P1+0.000000000001) + peakSeparation-setpoint1) * P1;  }
      
      // Serial.print("Time separation is ");
      // Serial.print(peakSeparation, 3);
      // Serial.print(" ms; ");    
      // Serial.print(", ");
      // Serial.println(feedback, 4);
      // Serial.print(" (Set point: ");
      // Serial.print(setpoint1);
      // Serial.print(", P1:");
      // Serial.print(P1, 4);
      // Serial.print(", Threshold: ");
      // Serial.print(Vth);
      // Serial.print(", Trigger Period: ");
      // Serial.print(period);
      // Serial.println(")");  

      writeDAC(2, feedback);
    }  
  }
  secondPreviousSignalValue = previousSignalValue;
  previousSignalValue = currentSignalValue;
}

void loop() {
  qC.readSerial(Serial);  
  static unsigned long lastrun = 0;    
	if (millis() > lastrun) { 
    	lastrun = millis() + 5*period;
	    toggleLEDGreen();
         Serial.print(peakSeparation, 3);         Serial.println(", ");
        //  Serial.print(feedback, 4);         Serial.print(", ");
        //  Serial.print(setpoint1, 4);          Serial.print(", ");
        //  Serial.println(period, 4);
	}
}