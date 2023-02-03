class DDS():
   def __init__(self, urukul_idx, ch, freq_MHz=0, att_dB=0):
      self.uidx = urukul_idx
      self.ch = ch
      self.freq_MHz = freq_MHz
      self.att_dB = att_dB
      
   def name(self): 
      return f'urukul{self.uidx}_ch{self.ch}'