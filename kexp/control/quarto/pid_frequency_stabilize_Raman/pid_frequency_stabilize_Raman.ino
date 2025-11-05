#include "qCommand.h"

qCommand qC;
IntervalTimer DAC_Timer; 
IntervalTimer plot;

volatile bool trigger1Activated = false;
double currentSignalValue = 0;
double peakSeparation = 0;
double feedback = 0;
double er = 0, i_er = 0, d_er = 0;

double Vth = 1;
double G1 = 1;
double P1 = 0.01;
double I1 = 0.0;
double D1 = 0.0;
double setpoint1 = 36;
double Lock = 1;

unsigned long lastRisingEdgeTime = 0;
unsigned long currentRisingEdgeTime = 0;
unsigned long period = 0;
int lastState = LOW;

void setup() {
  configureADC(1, 1, 0, BIPOLAR_10V, getADC1);

  qC.assignVariable("sep", &peakSeparation);
  qC.assignVariable("setp", &setpoint1);
  qC.assignVariable("vth", &Vth);
  qC.assignVariable("g1", &G1);
  qC.assignVariable("p1", &P1);
  qC.assignVariable("i1", &I1);
  qC.assignVariable("d1", &D1);
  qC.assignVariable("lock", &Lock);

  enableInterruptTrigger(1, BOTH_EDGES, hold1);
}

void hold1() {
  if (triggerRead(1)) trigger1Activated = true;
}

void getADC1() {
  currentSignalValue = readADC1_from_ISR();
}

void update() {
  static double prevVal = 0, prev2Val = 0;
  static double firstPeakTime = 0, secondPeakTime = 0;
  static bool firstDetected = false;

  const double currentTime = micros() / 1000.0;
  const int triggerState = triggerRead(1);

  // Detect period by rising edges
  if (lastState == LOW && triggerState == HIGH) {
    currentRisingEdgeTime = currentTime;
    if (lastRisingEdgeTime) period = currentRisingEdgeTime - lastRisingEdgeTime;
    lastRisingEdgeTime = currentRisingEdgeTime;
    firstDetected = false;
    firstPeakTime = secondPeakTime = 0;
  }
  lastState = triggerState;

  // Peak detection
  const bool isPeak = (prevVal > prev2Val && prevVal > currentSignalValue && prevVal > Vth);
  if (!isPeak) {
    prev2Val = prevVal;
    prevVal = currentSignalValue;
    return;
  }

  if (!firstDetected) {
    firstDetected = true;
    firstPeakTime = currentTime;
  } else if (currentTime - firstPeakTime > 2 && !secondPeakTime) {
    secondPeakTime = currentTime;
    peakSeparation = secondPeakTime - firstPeakTime;

    if (Lock == 1 && fabs(feedback) < 1.5) {
      const double errNow = peakSeparation - setpoint1;
      i_er += errNow;
      d_er = errNow - er;
      er = errNow;
      feedback += (P1 * er + I1 * i_er + D1 * d_er) * G1;
    } else {
      feedback = 0;
    }
    writeDAC(1, feedback);
  }

  prev2Val = prevVal;
  prevVal = currentSignalValue;
}

void loop() {
  static bool timerStarted = false;
  static unsigned long lastPrint = 0;

  if (trigger1Activated && !timerStarted) {
    plot.end();
    plot.begin(update, 10);
    timerStarted = true;
    trigger1Activated = false;
  }

  qC.readSerial(Serial);

  if (millis() - lastPrint >= 10 * (period ? period : 1)) {
    lastPrint = millis();
    toggleLEDGreen();
    Serial.print(peakSeparation, 3); Serial.print(", ");
    Serial.print(er, 3); Serial.print(", ");
    Serial.println(feedback, 4);
  }
}
