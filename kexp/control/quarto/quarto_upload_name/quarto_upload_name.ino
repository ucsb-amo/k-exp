#include "qCommand.h"
qCommand qC;

struct Cal {
    uint16_t cal_a;
    double cal_b;
    uint16_t cal_c;
    char cal_d[16] = "raman_pid"; // label the quarto here
}; 
struct Cal cal1; // Properly declare the cal1 variable

void setup() {
  Serial.begin(115200); // Initialize serial communication
  
  cal1.cal_a = 56;//various numbers to test storage is working
  cal1.cal_b = 1.2345678;
  cal1.cal_c = 9876;

  writeNVMpages(&cal1, sizeof(cal1), 500); //Store struct cal1 in NVM starting at page 500
  Serial.printf("Checking cal_a in NVM is: %u\n", readNVM(500*128));

}