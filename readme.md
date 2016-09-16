Thrust Disassembly
===

Thrust
By Jeremey C. Smith

Source disassembly & documentation by Kieran HJ Connell, February 2016
Initial disassembly created using BeebDis by Phill Harvey-Smith
Verified to compile using BeebAsm by Rich Talbot-Watkins
With thanks to jms2 for his original Thrust disassembly notes and
Matt Godbolt for his encouragement for me to get this released!

Notes
=
Original $.THRUST3 executable had to first be decrypted
Relocated from load address $1A00 to executation address $A60
Relocation code modified slightly as no longer encrypted
Source documented and annotated for first release

Build
=
> beebasm.exe -i thrust.6502 -do thrust.ssd -boot Thrust -v

Details
=
_LO & _HI used to identify low byte & high byte of 16-bit values & pointers

Most calculations are in Q7.8 fixed-point arithmetic although y values are
stored in Q10.8 as each world can be several screens deep. Some physics
calculations are performed Q7.16  in x to provide additional precision.
_FRAC & _INT are used to identify the fraction and integer components of a
fixed-point variable. _FRAC_LO is used to signify an additional byte of
precision at the low end whilst _INT_HI is used for additional upper bits.

To do
= 
* Properly document each function and how each routine actually works
* Identify remaining zero page variables
* Extract constants and globals from immediates
* Sleep