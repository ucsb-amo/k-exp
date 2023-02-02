from artiq import *
import sys, getopt

def main(argv):
   inputfile = ''
   outputfile = ''
   opts, args = getopt.getopt(argv,"f:",["ifile=","ofile="])
   for opt, arg in opts:
      if opt == '-h':
         
         sys.exit()
         

if __name__ == "__main__":
   main(sys.argv[1:])