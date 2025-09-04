#
# Chinese Digital Calliper Decoder with Timing-Based Pulse Classification
#
# Author: Tim Jackson.1960
# Date: 2024-09-04
# License: GPLv2+
#

import sigrokdecode as srd


class Decoder(srd.Decoder):
    api_version = 3
    id = "calliper_CN"
    name = "Callipers CN"
    longname = "Chinese Calliper Decoder"
    desc = "Classifies pulse types from Chinese digital callipers using timing."
    license = "gplv2+"
    inputs = ["logic"]
    outputs = []
    channels = (
        {"id": "clock", "name": "Clock", "desc": "Clock signal from calliper"},
        {"id": "data", "name": "Data", "desc": "Data signal from calliper"},
    )
    options = ()
    tags = ["Embedded/Industrial", "Util"]
    annotations = (
        ("bitPulse", "Bit Pulse"),          # ID 0
        ("bitSpacer", "Bit Spacer"),        # ID 1
        ("bitValue", "Bit Value"),          # ID 2
        ("seperators", "Header Footer"),    # ID 3
        ("binary", "Binary Value (Note! LSB comes first)"), # ID 4
        ("nul", "Null State"),              # ID 5
        ("raw", "Raw Calliper Units (Binary flipped)"),     # ID 6
        ("con", "Converted Data (Caliper units converted)"),# ID 7
    )
    annotation_rows = (
        ("pulses", "Pulse Types", (0,1,2,3,5,)),
        ("bits", "Bit Values", (4,)),
        ("rawValues", "Raw Values", (6,)),
        ("convertedValues", "Converted Values", (7,)),
    )
            
    frame_index = 0
    frame_separator_detected = False

    def __init__(self):
        self.reset()

    def reset(self):
        self.samplerate = None
        self.last_state = None
        self.last_sample = None
        self.null_detected = True
        self.ranges = {}

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)

        # Calculate µs per sample
        sample_us = 1e6 / self.samplerate

        # Define timing ranges with adjusted lower bounds
        self.ranges = {
            "Bit_Pulse": (max(2, 4 - sample_us), 6),
            "Header_Footer": (max(40, 50 - sample_us), 60),
            "Frame_Seperator": (max(80, 100 - sample_us), 120),
            "Null_State": (1000, float("inf")),
            "BitSpacer": (max(5, 7 - sample_us), 9),
        }

    def decode(self):
        
        bit_buffer = []
        bit_start_sample = None
        bit_end_sample = None
        collecting = False

        #raw * 20000 / 40970 imperial
        #raw * 2000 / 1613 metric
        conversion_units = {
            "metric": 1613,
            "imperial": 40970,
        }

        # Force both annotation rows to appear
        self.put(0, 1, self.out_ann, [0, ["init"]])
        self.put(0, 1, self.out_ann, [1, ["init"]])
        self.put(0, 1, self.out_ann, [2, ["init"]])
        self.put(0, 1, self.out_ann, [3, ["init"]])

        if self.samplerate is None:
            raise Exception("Cannot decode without samplerate.")

        while True:

            clk, data = self.wait([{0: "e"}, {0: "r"}])  # Wait for edge on clock

            clk_sample = self.samplenum
            clk_level = self.matched[1]

            try:
                data_level = data
            except IndexError:
                data_level = None  # Graceful fallback

            if self.last_state is not None:
                duration = (clk_sample - self.last_sample) * 1e6 / self.samplerate

                # ===   Rising edge ===========

                if clk_level == 1:  
                    if (
                        self.ranges["Header_Footer"][0]
                        <= duration
                        <= self.ranges["Header_Footer"][1]
                    ):
                        label = "Header" if self.null_detected else "Footer"
                        self.put(
                            self.last_sample, clk_sample, self.out_ann, [3, [label]]
                        )

                        if label == "Footer":
                           collecting = False
                           self.frame_index = 0

                        self.null_detected = False
                    elif (
                        self.ranges["Frame_Seperator"][0]
                        <= duration
                        <= self.ranges["Frame_Seperator"][1]
                    ):
                        self.put(
                            self.last_sample,
                            clk_sample,
                            self.out_ann,
                            [3, ["Frame Seperator"]],
                        )
                        self.frame_separator_detected = True
                        collecting = False

                    elif (
                        self.ranges["BitSpacer"][0]
                        <= duration
                        <= self.ranges["BitSpacer"][1]
                    ):
                        self.put(
                            self.last_sample,
                            clk_sample,
                            self.out_ann,
                            [1, ["Bit Spacer"]],
                        )
                    else:
                        # Unexpected duration — maybe log or skip
                        pass 
                   
                    # ===   Falling edge    ==========

                elif clk_level == 0:
                    if (self.ranges["Bit_Pulse"][0] <= duration <= self.ranges["Bit_Pulse"][1]):

                        self.put(self.last_sample, clk_sample, self.out_ann, [0, ["Bit Pulse"]],)
                        self.put(self.last_sample, clk_sample, self.out_ann, [4, [str(data_level)]],)

                        if not collecting and (self.null_detected or self.frame_separator_detected):
                            collecting = True
                            bit_buffer = []
                            bit_start_sample = self.last_sample


                        # Inside your decoding loop:
                        if collecting:
                            bit_buffer.append(str(data_level))
                            if len(bit_buffer) == 24:
                                bit_end_sample = clk_sample
                                # binary_str = "".join(bit_buffer)
                                binary_str = "".join(reversed(bit_buffer))
                                value = int(binary_str, 2)
                                if binary_str[0] == "1":
                                    value -= 1 << 24  # two's complement correction

                                # Emit binary + decimal label
                                label = "{} = {}".format(binary_str, value)
                                self.put(bit_start_sample, bit_end_sample, self.out_ann, [6, [label]])

                                # Only label converted value on first frame
                                if self.frame_index == 0:
                                    self.frame_index = 1
                                    mm_value = (value * 2) / conversion_units["metric"]
                                    converted_label = "6mm Calibration offset = {:.2f} mm".format(mm_value)
                                    self.put(bit_start_sample, bit_end_sample, self.out_ann, [7, [converted_label]])
                                else:
                                    mm_value = (value * 2) / conversion_units["metric"]
                                    inch_value = (value * 2) / conversion_units["imperial"]
                                    converted_label = "Relative values = {:.2f} mm / {:.4f} in".format(mm_value, inch_value)
                                    self.put(bit_start_sample, bit_end_sample, self.out_ann, [7, [converted_label]])
                                    self.frame_separator_detected = False  # reset after use

                                bit_buffer = []
                                collecting = False


                    elif (
                        self.ranges["Null_State"][0]
                        <= duration
                        <= self.ranges["Null_State"][1]
                    ):
                        self.put(
                            self.last_sample,
                            clk_sample,
                            self.out_ann,
                            [5, ["Null State"]],
                        )
                        self.null_detected = True
                    else:
                        # Unexpected duration — maybe log or skip
                        pass
                else:
                    # Unexpected level — maybe log or skip
                    pass

            self.last_state = clk_level
            self.last_sample = clk_sample
