#include "qCommand.h"
qCommand qC;
IntervalTimer DAC_Timer; 
IntervalTimer plot;

double integral1 = 0;
double currentSignalValue = 0;

bool integrator_go1 = true;

float Vth = 0.5;
float P1 = 0.0;
double setpoint1 = 50;
double newadc1 = 0;

unsigned long firstPeakTime = 0;
unsigned long secondPeakTime = 0;
bool firstPeakDetected = false;
unsigned long startTime = 0;



void setup() {
  configureADC(1,1,0,BIPOLAR_5V,getADC1);

  qC.assignVariable("setp",&setpoint1);
  qC.assignVariable("vth",&Vth);
  qC.assignVariable("p1",&P1);

  enableInterruptTrigger(1,BOTH_EDGES,&hold1);

  qC.addCommand("c",clear_integrator);
}

void clear_integrator(qCommand& qC, Stream& S) {
  integral1 = 0;
}

void hold1() {
  if (triggerRead(1)) {
    integral1 = 0;
    integrator_go1 = false;
    plot.begin(update, 1e1);
  } else {
    integrator_go1 = true;
  }
}

void getADC1(void) {
  double newadc1 = readADC1_from_ISR(); //read ADC voltage
  currentSignalValue = newadc1;
}

void update(void) {
  static double previousSignalValue = 0;
  static double secondPreviousSignalValue = 0;
  unsigned long currentTime = millis();
  // Serial.println(currentSignalValue);
  if (currentTime - startTime >= 240) {
    startTime = currentTime;
    firstPeakDetected = false;
    firstPeakTime = 0;
    secondPeakTime = 0;
  }

  if ( triggerRead(1)==1 && previousSignalValue > currentSignalValue && previousSignalValue > secondPreviousSignalValue && previousSignalValue > Vth) {
    if (!firstPeakDetected) {
      firstPeakTime = currentTime;
      firstPeakDetected = true;      
      delay(2);
    } 
    else if (firstPeakDetected && secondPeakTime == 0) {
      secondPeakTime = currentTime;
      Serial.print("First peak found at ");
      Serial.print(firstPeakTime - startTime);
      Serial.print(" ms; ");

      Serial.print("Second peak found at ");
      Serial.print(secondPeakTime - startTime);
      Serial.print(" ms; ");

      double peakSeparation = secondPeakTime - firstPeakTime;
      float feedback = (peakSeparation-setpoint1)*P1;
      
      if (feedback > 0.1){ feedback = 0; 
      } else if (feedback < -0.1) { feedback = 0; }
      Serial.print("Time separation is ");
      Serial.print(peakSeparation);
      Serial.print(" ms; ");    
      Serial.print("Feedback signal is ");
      Serial.print(feedback, 4);
      Serial.print(" (Set point: ");
      Serial.print(setpoint1);
      Serial.print(", P1:");
      Serial.print(P1, 4);
      Serial.print(", Threshold: ");
      Serial.print(Vth);
      Serial.println(")");  

      writeDAC(1, feedback);
    }  
  }
  secondPreviousSignalValue = previousSignalValue;
  previousSignalValue = currentSignalValue;
}

void loop() {
  qC.readSerial(Serial);  
}