// Host check: the interlock firmware v2 reports byte for byte what v1 printed.
//
// Built and run by tests/test_interlock_firmware_report.py with the Opta core's
// own Print.cpp, so numbers are formatted exactly as on the Opta.
//
// Runs the same cycles through v1's code (copied below) and v2's, each keeping
// its own trip, and compares the text. v2's code is interlock_logic.h: the
// test copies it out of the sketch's "What trips and what is reported" section.
// Then writes sample v2 reports to the folder given as argv[1] for the Python
// side to parse with the server's parser:
//   sample_NN.txt   the report
//   samples.txt     one line per sample: NN temperature_k flow1 flow2 flow3 flow4 tripped
//
// Exit 0: all equal. Exit 1: the first difference is printed.

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

#include "Print.h"
using namespace arduino;
#include "interlock_logic.h"  // the sketch's section, copied by the test

// A Print into a std::string (stands in for Serial).
class StringOut : public Print {
public:
  using Print::write;
  size_t write(uint8_t c) override {
    text += (char)c;
    return 1;
  }
  std::string text;
};

// v1's loop(), copied from ../interlock-arduino-code/interlock-arduino-code.ino.
// Changes: Serial is a StringOut; the analog reads are replaced by the given
// values; the pin writes and delays are removed. Everything printed is as v1.
struct V1 {
  const float tempUpperBound = 306;
  const float tempLowerBound = 280;
  const float flowLowerBound = 3.0;
  const float flowUpperBound = 8.0;
  bool isTripped = false;

  std::string cycle(float temp, const float flows_in[4]) {
    StringOut Serial;
    float flows[4] = {flows_in[0], flows_in[1], flows_in[2], flows_in[3]};

    Serial.print("/Temp is ");
    Serial.print(temp,5);
    Serial.println("k/");

    if (temp>tempUpperBound|| temp < tempLowerBound )
    {
      Serial.println("SHUTTING OFF POWER SUPPLY DUE TO TEMPERATURE");
      isTripped = true;
    }

    for(int i=0; i<4; i++)
    {
      Serial.print("/Flowmeter ");
      Serial.print(i+1);
      Serial.print(" reads ");
      Serial.print(flows[i]);
      Serial.println("V/");
      if(flows[i]<flowLowerBound || flows[i]>flowUpperBound)
      {
        Serial.print("SHUTTING OFF POWER SUPPLY DUE TO FLOW RATE of flowmeter ");
        Serial.print(i+1);
        Serial.println(" being out of bounds");
        isTripped = true;
      }
    }

    if(isTripped)
    {
      Serial.println("I TRIPPED");
    }
    return Serial.text;
  }
};

// v2: the firmware's own code, written through the same TextBuffer the Opta uses.
struct V2 {
  Status st;

  std::string cycle(float temp, const float flows[4]) {
    st.temperature_k = temp;
    for (int i = 0; i < N_FLOWS; i++) st.flow_v[i] = flows[i];
    checkLimits(st);
    TextBuffer report;
    writeReport(report, st);
    return std::string(report.text, report.length);
  }
};

struct Reading {
  float temp;
  float flows[4];
};

// The largest values the inputs can give: full scale 3.5 V / 0.3034 = 11.54 V.
const float V_MAX = 3.5f / 0.3034f;
const float T_MAX = 293.0f * V_MAX / 1.465f;

static float uniform(float lo, float hi) { return lo + (hi - lo) * (float)rand() / (float)RAND_MAX; }

// Mostly near the limits, sometimes anywhere in the input range.
static float randomTemp() {
  switch (rand() % 4) {
    case 0: return uniform(279.9f, 280.1f);
    case 1: return uniform(305.9f, 306.1f);
    case 2: return uniform(0.0f, T_MAX);
    default: return uniform(285.0f, 300.0f);
  }
}
static float randomFlow() {
  switch (rand() % 4) {
    case 0: return uniform(2.99f, 3.01f);
    case 1: return uniform(7.99f, 8.01f);
    case 2: return uniform(0.0f, V_MAX);
    default: return uniform(3.5f, 7.5f);
  }
}

static int fail(const char *what, int n, const std::string &v1, const std::string &v2) {
  printf("DIFFERENT (%s, cycle %d)\n--- v1 ---\n%s--- v2 ---\n%s---\n", what, n, v1.c_str(), v2.c_str());
  return 1;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    printf("usage: report_equivalence <sample folder>\n");
    return 2;
  }
  const std::string folder = argv[1];

  // Fixed sequences; the trip carries over within a sequence, as on the Opta.
  const std::vector<std::vector<Reading>> sequences = {
    {{293.12345f, {4.56f, 5.0f, 6.0f, 7.0f}}},                        // normal
    {{280.0f, {3.0f, 3.0f, 8.0f, 8.0f}}, {306.0f, {8.0f, 3.0f, 3.0f, 8.0f}}},  // exactly at the limits
    {{306.01f, {5, 5, 5, 5}}, {293.0f, {5, 5, 5, 5}}},              // temperature high, then normal: still tripped
    {{279.99f, {5, 5, 5, 5}}},                                       // temperature low
    {{293.0f, {2.99f, 5, 5, 5}}, {293.0f, {5, 5, 5, 5}}},            // flow 1 low, then normal
    {{293.0f, {5, 5, 5, 8.01f}}},                                    // flow 4 high
    {{0.0f, {0, 0, 0, 0}}},                                          // everything at zero (open inputs)
    {{T_MAX, {V_MAX, V_MAX, V_MAX, V_MAX}}},                         // everything at full scale
  };

  int n = 0;
  size_t longest = 0;
  for (const auto &sequence : sequences) {
    V1 v1;
    V2 v2;
    for (const auto &r : sequence) {
      std::string a = v1.cycle(r.temp, r.flows), b = v2.cycle(r.temp, r.flows);
      if (a != b) return fail("fixed", n, a, b);
      if (b.size() > longest) longest = b.size();
      n++;
    }
  }

  // Random sequences of 50 cycles.
  srand(1);
  std::vector<Reading> samples;
  std::vector<bool> sample_tripped;
  for (int s = 0; s < 400; s++) {
    V1 v1;
    V2 v2;
    for (int c = 0; c < 50; c++) {
      Reading r = {randomTemp(), {randomFlow(), randomFlow(), randomFlow(), randomFlow()}};
      std::string a = v1.cycle(r.temp, r.flows), b = v2.cycle(r.temp, r.flows);
      if (a != b) return fail("random", n, a, b);
      if (b.size() > longest) longest = b.size();
      n++;

      if (s < 4 && c < 10) {
        // Keep 40 for the parser check, the report's text with them.
        int k = (int)samples.size();
        samples.push_back(r);
        sample_tripped.push_back(v2.st.tripped);
        char path[512];
        snprintf(path, sizeof(path), "%s/sample_%02d.txt", folder.c_str(), k);
        FILE *f = fopen(path, "wb");
        if (!f) { printf("cannot write %s\n", path); return 2; }
        fwrite(b.data(), 1, b.size(), f);
        fclose(f);
      }
    }
  }

  FILE *index = fopen((folder + "/samples.txt").c_str(), "w");
  if (!index) { printf("cannot write samples.txt\n"); return 2; }
  for (size_t k = 0; k < samples.size(); k++) {
    const Reading &r = samples[k];
    fprintf(index, "%02d %.9g %.9g %.9g %.9g %.9g %d\n", (int)k, r.temp,
            r.flows[0], r.flows[1], r.flows[2], r.flows[3], sample_tripped[k] ? 1 : 0);
  }
  fclose(index);

  printf("equal: %d cycles; longest report %zu bytes (REPORT_MAX %zu)\n", n, longest, REPORT_MAX);
  return longest < REPORT_MAX ? 0 : 1;
}
