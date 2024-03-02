call %kpy%
B:
cd %data%
artiq_master --experiment-subdir %code%/k-exp/kexp/experiments --device-db %db% 