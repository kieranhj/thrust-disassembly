@..\..\Bin\beebasm.exe -i thrust.6502 -do thrust.ssd -boot Thrust -v
@.\crc32dos.exe thrust.ssd
@echo 6389c446
