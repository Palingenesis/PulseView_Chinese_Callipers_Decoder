
# __init__.py for Chinese Callipers decoder

'''
Chinese Digital Caliper Decoder
Author: Tim Jackson.1960

This decoder interprets the basic Chinese digital caliper protocol.

Signal Notes:
- Data and clock lines must be connected through a logic level shifter.
- This inverts the signals: logic high = 1, logic low = 0.
- During the Null state, both lines are held high.
- Both lines are pulled low before data transmission begins.

Protocol Overview:
- Clock pulses high for each bit.
- Data is sent LSB first.
- Each burst contains 2 frames of 24 bits:
    - Frame 1: Calibration data
    - Frame 2: Measurement data
'''

from .calliper_CN import Decoder
