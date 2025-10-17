/**
  Opta's Analog Input Terminals
  Name: opta_analog_inputs_example.ino
  Purpose: This sketch demonstrates the use of I1, I2, and I3 input 
  terminals as analog inputs on Opta.

  @author Arduino PRO Content Team
  @version 2.0 22/07/23
*/

//import processing.serial.*;

// constants that enable correct reading of analog pins, I don't understand divider but it seems to be neccessary to correctly read the pins. These numbers agree with a multimeter (I think!)
const float VOLTAGE_MAX   = 3.5;    // Maximum voltage that can be read
const float RESOLUTION    = 65535.0;   // 12-bit resolution
const float DIVIDER       = 0.3034;      // Voltage divider

const float tempBase = 293;//k
const float voltBase = 1.465;

float flows[] = {4,4,4,4};

float voltage;
float bleh =330.1;
// Array of terminals.
const int TERMINALS[] = {A0, A1, A2, A3, A4, A5, A6};

const float tempUpperBound = 303;
const float tempLowerBound = 280;
const float flowLowerBound = 3.0;
const float flowUpperBound = 8.0;

bool isTripped = false;


// Number of terminals.
const int NUM_PINS = 5;

#define safPin D3
#define relayPin D1



void setup() {
  // Initialize serial communication at 9600 bits per second.
  Serial.begin(9600);
  delay(500);
  //Serial.println("Starting interlock");
  //Open the failsafe relay, if the PLC loses power, this will close which will short the magnetsf
  digitalWrite(safPin, HIGH);
  digitalWrite(relayPin, HIGH);

  // Enable analog inputs on Opta
  // Set the resolution of the ADC to 12 bits.
  analogReadResolution(16);
  //flows = new float[4];
}

void loop() {
  //Serial.begin(9600);
  //RTD is at terminal 0
  float v = readAndPrint(TERMINALS[0]);
  //convert voltage to temperature
  // when v= 1.465, t = 293k
  float temp = tempBase*v/voltBase;
  Serial.print("/Temp is ");
  Serial.print(temp,5);
  Serial.println("k/");

  //Get flow meter voltages
  flows[0] = readAndPrint(TERMINALS[2]);
  flows[1] = readAndPrint(TERMINALS[3]);
  flows[2] = readAndPrint(TERMINALS[4]);
  flows[3] = readAndPrint(TERMINALS[5]);
  

  ///If temp too high or low shut off magnets
  if (temp>tempUpperBound|| temp < tempLowerBound )
  {
    //Serial.println("SHUTTING OFF POWER SUPPLY DUE TO TEMPERATURE");
    digitalWrite(safPin, LOW);
    isTripped = true; 
  }

  ///Keeping flows as voltages
  for(int i=0; i<4; i++)
  {
    Serial.print("/Flowmeter ");
    Serial.print(i+1);
    Serial.print(" reads ");
    Serial.print(flows[i]);
    Serial.println("V/");
    if(flows[i]<flowLowerBound || flows[i]>flowUpperBound)
    {
      // Serial.print("SHUTTING OFF POWER SUPPLY DUE TO FLOW RATE of flowmeter ");
      // Serial.print(i+1);
      // Serial.println(" being out of bounds");
      digitalWrite(safPin, LOW);
      isTripped = true;
    }
    delay(200);
  }

  if (Serial.available() > 0) {
    // read the incoming byte: bite 
    int incomingByte = Serial.read();    
    // say what you got:
    //Serial.print("I received: ");
    //Serial.println(incomingByte, DEC);
    ///Manually switch magnets back on, if tripped, will imediiately switch off
    if(incomingByte == 79)
    {
        isTripped = false;
        digitalWrite(safPin, HIGH);
    }
  }
  if(isTripped)
  {
    Serial.println("I TRIPPED");
  }

  // Delay for half a second before reading the terminals again.
  //delay(500);
}

// This function reads the value from the specified pin, converts it to voltage, and prints the result.
float readAndPrint(int terminal) {
  // Read the input value from the analog pin.
  int terminalValue = analogRead(terminal);

  // Convert the terminal value to its corresponding voltage. 
  voltage = terminalValue * (VOLTAGE_MAX / RESOLUTION) / DIVIDER;


  //Serial.println(voltage,5);
  return voltage;
}
