# ANL:waggle-license
# This file is part of the Waggle Platform.  Please see the file
# LICENSE.waggle.txt for the legal details of the copyright and software
# license.  For more details on the Waggle project, visit:
#          http://www.wa8.gl
# ANL:waggle-license
import threading
import serial
import sys
import time
import Queue
import struct

import numpy
import math

from RTlist import getRT

_preamble = '\xaa'
_postScript = '\x55'

_datLenFieldDelta = 0x02
_protVerFieldDelta = 0x01
_msgCRCFieldDelta = 0x01
_msgPSDelta = 0x02
_maxPacketSize = 256

__lenFmt1 = 2
__lenFmt2 = 2
__lenFmt3 = 6
__lenFmt4 = 3
__lenFmt5 = 3
__lenFmt6 = 2
__lenFmt7 = 4
__lenFmt8 = 3

# sensor_list = ["Board MAC","TMP112","HTU21D","GP2Y1010AU0F","BMP180","PR103J2","TSL250RD","MMA8452Q","SPV1840LR5H-B","TSYS01","HMC5883L","HIH6130","APDS-9006-020","TSL260RD","TSL250RD","MLX75305","ML8511","D6T","MLX90614","TMP421","SPV1840LR5H-B","Total reducing gases","Ethanol (C2H5-OH)","Nitrogen Di-oxide (NO2)","Ozone (03)","Hydrogen Sulphide (H2S)","Total Oxidizing gases","Carbon Monoxide (C0)","Sulfur Dioxide (SO2)","SHT25","LPS25H","Si1145","Intel MAC"]
sensor_list = ["Board_MAC","TMP112","HTU21D","HIH4030","BMP180","PR103J2","TSL250RD","MMA8452Q","SPV1840LR5H-B","TSYS01","HMC5883L","HIH6130","APDS-9006-020","TSL260RD","TSL250RD","MLX75305","ML8511","D6T","MLX90614","TMP421","SPV1840LR5H-B","Total reducing gases","Ethanol (C2H5-OH)","Nitrogen Di-oxide (NO2)","Ozone (03)","Hydrogen Sulphide (H2S)","Total Oxidizing gases","Carbon Monoxide (C0)","Sulfur Dioxide (SO2)","SHT25","LPS25H","Si1145","Intel MAC","CO ADC temp","IAQ/IRR ADC temp","O3/NO2 ADC temp","SO2/H2S ADC temp","CO LMP temp","Accelerometer","Gyroscope", "alpha histo", "alpha firmware", "alpha conf a", "alpha conf b", "alpha conf c", "alpha conf d"]
#decoded_output = ['0' for x in range(16)]

#### alpha        
def lininterp(a, b, n):
    assert isinstance(n, int) and n > 1
    return tuple(a + i * (b - a) / (n - 1) for i in range(n))

bin_sizes = lininterp(0.38, 17.0, 16)
bin_units = {
    'bins': 'particle / second',
    'mtof': 'second',
    'sample flow rate': 'sample / second',
    'pm1': 'microgram / meter^3',
    'pm2.5': 'microgram / meter^3',
    'pm10': 'microgram / meter^3',
    'temperature': 'celcius',
    'pressure': 'pascal',
}


def format1 (input):
    #F1 - unsigned int_16 output, {0-0xffff} - Byte1 Byte2 (16 bit number)
    byte1 = ord(input[0])
    byte2 = ord(input[1])
    value = (byte1 << 8) | byte2
    return value


def format2 (input):
    #F2 - int_16 output , +-{0-0x7fff} - 1S|7Bits Byte2
    byte1 = ord(input[0])
    byte2 = ord(input[1])
    value = ((byte1 & 0x7F) << 8 ) | byte2
    if byte1 & 0x80 == 0x80:
        value = value * -1
    return value

def format3 (input):
    #F3 - hex string, {0-0xffffffffffff} - Byte1 Byte2 Byte3 Byte4 Byte5 Byte6
    return str(hex(ord(input)))[2:]

def format4 (input):
    #F4 - unsigned long_24 input, {0-0xffffff} - Byte1 Byte2 Byte3
    byte1 = ord(input[0])
    byte2 = ord(input[1])
    byte3 = ord(input[2])
    value = (byte1 << 16) | (byte2 << 8) | (byte3)
    return value

def format5 (input):
    #F5 - long_24 input, +-{0-0x7fffff} - 1S|7Bits Byte2 Byte3
    byte1 = ord(input[0])
    byte2 = ord(input[1])
    byte3 = ord(input[2])
    value = ((byte1 & 0x7F) << 16) | (byte2 << 8) | (byte3)
    if byte1 & 0x80 == 0x80:
        value = value * -1
    return value

def format6 (input):
    #F6 - float input, +-{0-127}.{0-99} - 1S|7Bit_Int 0|7Bit_Frac{0-99}
    byte1 = ord(input[0])
    byte2 = ord(input[1])
    #have to be careful here, we do not want three decimal placed here.
    value = (byte1 & 0x7F) + (((byte2 & 0x7F) % 100) * 0.01)
    if (byte1 & 0x80) == 0x80:
        value = value * -1
    return value

def format7 (input):
    #F7 - byte input[4], {0-0xffffffff} - Byte1 Byte2 Byte3 Byte4
    byte1 = ord(input[0])
    byte2 = ord(input[1])
    byte3 = ord(input[0])
    byte4 = ord(input[1])
    value = [byte1,byte2,byte3,byte4]
    return value

def format8 (input):
    #F8 - float input, +-{0-31}.{0-999} - 1S|5Bit_Int|2MSBit_Frac  8LSBits_Frac
    byte1 = ord(input[0])
    byte2 = ord(input[1])
    value = ((byte1 & 0x7c) >> 2) + ( ( ((byte1 & 0x03) << 8) | byte2 ) * 0.001)
    if (byte1 & 0x80) == 0x80:
        value = value * -1
    return value

def decode17(data):

    data = bytearray(data)

    bincounts = struct.unpack_from('<16B', data, offset=0)
    checksum = struct.unpack_from('<H', data, offset=48)[0]
    mtof = [x / 3 for x in struct.unpack_from('<4B', data, offset=32)]
    sample_flow_rate = struct.unpack_from('<I', data, offset=36)[0]
    pmvalues = struct.unpack_from('<fff', data, offset=50)
    pressure = struct.unpack_from('<I', data, offset=40)[0]
    temperature = pressure / 10.0


    values = {
        'bins': bincounts,
        'mtof': mtof,
        'sample flow rate': sample_flow_rate,
        'pm1': pmvalues[0],
        'pm2.5': pmvalues[1],
        'pm10': pmvalues[2],
        'error': sum(bincounts) & 0xFF != checksum,
    }

    if temperature > 200:
        values['pressure'] = pressure
    else:
        values['temperature'] = temperature

    return values

def alphasense_histo(raw_data):
    data = decode17(raw_data)

    for size, count in zip(bin_sizes, data['bins']):
        print('{: 3.4f} {:>6}'.format(size, count))
    print()

    for pm in ['pm1', 'pm2.5', 'pm10']:
        print('{} {}'.format(pm, data[pm]))
    print()

    print(data)
    print(repr(raw_data))


def firmware_version(input):
    byte1 = ord(input[0])
    byte2 = ord(input[1])

    hw_maj_version = byte1 >> 5
    hw_min_version = (byte1 & 0x1C) >> 2

    fw_maj_version = ((byte1 & 0x03) << 2) | ((byte2 & 0xC0) >> 6)
    fw_min_version = byte2 & 0x3F

    if fw_min_version < 10:
        values = ((hw_maj_version * 10 + hw_min_version) * 10 + fw_maj_version) * 100 + fw_min_version
    else:
        values = ((hw_maj_version * 10 + hw_min_version) * 10 + fw_maj_version) * 10 + fw_min_version

    return values

def build_info_time(input):
    byte1 = ord(input[0])
    byte2 = ord(input[1])
    byte3 = ord(input[2])
    byte4 = ord(input[3])

    value = byte1 << 24 | byte2 << 16 | byte3 << 8 | byte4

    return value

def calc_input_voltage(input):
    # calc value before voltage divider, unit: V
    # MCP output code transform factor 0.065 mV/(uW/cm^2): MCP mux
    in_voltage = input * 0.0000625
    # voltage divider factor 5/2 to calc input voltage: voltage divider circuit
    out_from_sensor = (in_voltage * 5.00) / 2.00
    return out_from_sensor

def TSL260_irrad(input):
    # b = math.log10(0.06)
    # irrad = 10**(math.log10(input) - b)
    # print irrad

    # input unit: V, irrad unit: uW/cm^2
    irrad = (input - 0.006250) / 0.058
    # print irrad 

    return irrad

def TSL250_irrad_air(input):
    # a = (math.log10(0.04)-math.log10(0.6))/(math.log10(0.6)-1)
    # b = math.log10(3)/(a*math.log10(50))
    # irrad = 10**((math.log10(input) - b)/a)
    # print irrad

    # input unit: V, irrad unit: uW/cm^2
    irrad = input / 0.064
    # print irrad

    return irrad

def TSL250_irrad(input):
    # a = (math.log10(0.04)-math.log10(0.6))/(math.log10(0.6)-1)
    # b = math.log10(3)/(a*math.log10(50))
    # irrad = 10**((math.log10(input) - b)/a)
    # print irrad

    # input unit: V, irrad unit: uW/cm^2
    irrad = (input - 0.005781) / 0.064
    # print irrad

    return irrad

def APDS_irrad(input):
    irrad = input / 0.001944   # 405.1 unit: mA/lux
    return irrad


def parse_sensor (sensor_id,sensor_data):
#"Board MAC" "Board MAC"
    if sensor_id == '0':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        data = ''
        for i in range(len(sensor_data)):
            data = data + str(format3(sensor_data[i]))
        print  data

#firmware version
    elif sensor_id == "253":
        hw_sw_version = firmware_version(sensor_data[0:2])
        hw_ver = (hw_sw_version / 1000) / 10.
        fw_ver = (hw_sw_version - hw_ver * 10000) / 100.

        build_time = build_info_time(sensor_data[2:6])
        build_git = '{0:02x}'.format(format1(sensor_data[6:8]))

        print "Sensor:", sensor_id, "Firmware_version", '@ ',
        print hw_ver, fw_ver, build_time, build_git

    elif sensor_id == "252":
        tip_count = format1(sensor_data)
        rain_inches = float(tip_count) * 0.01

        print "Sensor:", sensor_id, "Rain_Gauger", ' @',
        print rain_inches

    elif sensor_id == "251":
        dielectric = format6(sensor_data[0:2])
        conductivity = format6(sensor_data[2:4])
        temperature = format6(sensor_data[4:6])

        volumetric_water_content = 4.3 * math.pow(10, -6) * math.pow(dielectric, 3) - 5.5 * math.pow(10, -4) * math.pow(dielectric, 2) + 2.92 * math.pow(10, -2) * dielectric - 5.3 * math.pow(10, -2)
        vwc = '{:2.4f}'.format(volumetric_water_content)

        print "Sensor:", sensor_id, "Decagon", ' @',
        print vwc, dielectric, conductivity, temperature



#alpha histo
    elif sensor_id == '40':
        print "Sensor:", sensor_id, sensor_list[int(sensor_id)], '@ '
        alphasense_histo(sensor_data)

#alpha firmware
    elif sensor_id == '41':
        print "Sensor:", sensor_id, sensor_list[int(sensor_id)], '@ ',
        print ord(sensor_data[0]), ord(sensor_data[1])

#alpha configuration
    elif sensor_id == '42':
        print "Sensor:", sensor_id, sensor_list[int(sensor_id)], '@ '
        alpha_config = sensor_data
    elif sensor_id == '43':
        alpha_config.extend(sensor_data)
    elif sensor_id == '44':
        alpha_config.extend(sensor_data)
    elif sensor_id == '45':
        alpha_config.extend(sensor_data)
        print alpha_config
                


#"TMP112" "TMP112"
    elif sensor_id == '1':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  format6(sensor_data)

#"HTU21D" "HTU21D"
    elif sensor_id == '2':
        HTU21D_temp = format6(sensor_data[0:0+__lenFmt6])
        HTU21D_humid = format6(sensor_data[0+__lenFmt6:0+__lenFmt6+__lenFmt6])
        HTU21D_compensate_humid = HTU21D_humid - (25 - HTU21D_temp) * 0.15
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print "{:2.2f}".format(HTU21D_temp), "{:2.2f}".format(HTU21D_compensate_humid)
#        print  format6(sensor_data[0:0+__lenFmt6]), format6(sensor_data[0+__lenFmt6:0+__lenFmt6+__lenFmt6])

#"GP2Y1010AU0F": REMOVED, NOT IN ANY VERSION
    # elif sensor_id == '3':
    #     print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
    #     print  format6(sensor_data[0:0+__lenFmt6]), format5(sensor_data[0+__lenFmt6:0+__lenFmt6+__lenFmt5])


#"HIH4030": how does the date format changed? "GP2Y1010AU0F" has been chaned
    elif sensor_id == '3':
        HIH4030_val = format1(sensor_data)
        HIH4030_voltage = (HIH4030_val * 5.0) / 1023.00    # extended exposure to > 90% RH causes a reversible shift of 3% RH
        HIH4030_humidity = (HIH4030_voltage - 0.85) * 100.00 / 3.00 # PUT DARK LEVEL VOLTAGE 0.85 FOR NOW
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print "{:2.2f}".format(HIH4030_humidity)

#"BMP180" "BMP180"
    elif sensor_id == '4':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  format6(sensor_data[0:0+__lenFmt6]), format5(sensor_data[0+__lenFmt6:0+__lenFmt6+__lenFmt5])

#"PR103J2" "PR103J2"
    elif sensor_id == '5':
        PR103J2_val = format1(sensor_data)
        try:
            temperature_PR = getRT(PR103J2_val)
        except Exception, e:
            print "ERROR", str(e)
            pass
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print "{:2.2f}".format(temperature_PR)
        # print  PR103J2_val,
        # print "{:10.2f}".format(47000*(1023.00/PR103J2_val - 1))

# #"TSL250RD" "TSL250RD"
    elif sensor_id == '6':        
        TSL250RD_1_voltage = (format1(sensor_data) * 3.3) / 1023.00
        TSL250RD_1_val = TSL250_irrad_air(TSL250RD_1_voltage)
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print "{:5.2f}".format(TSL250RD_1_voltage), "{:5.2f}".format(TSL250RD_1_val)

#"MMA8452Q" "MMA8452Q"
    elif sensor_id == '7':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  format6(sensor_data[0:0+__lenFmt6]), format6(sensor_data[0+__lenFmt6:0+__lenFmt6*2]),format6(sensor_data[0+__lenFmt6*2:0+__lenFmt6*3]),format6(sensor_data[0+__lenFmt6*3:0+__lenFmt6*4])

#"SPV1840LR5H-B" "SPV1840LR5H-B"
    elif sensor_id == '8':
        # print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        # print  format1(sensor_data)

        SPV_TSL_RAW = format1(sensor_data) * 3.3 / 1023.00         # raw voltage of TSL
        raw = SPV_TSL_RAW / 453.3333 - 1.65
        # V_I = (SPV_TSL_RAW - 1.75) / 453.33 - 1.75   # raw voltage of SPV
        # SPV_RAW = (-V_I * 1023.00) / 5.00          # raw integer [0, 1023] of SPV
        ############################################################################ Right till here
        # voltage_level = -numpy.log10(-V_I / 3.3) * 20.00 # sound lever in dB

        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print SPV_TSL_RAW, "{:2.6f}".format(raw)

#"TSYS01" "TSYS01"
    elif sensor_id == '9':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  format6(sensor_data)

#"HMC5883L" "HMC5883L"
    elif sensor_id == '10':
        HMC_x = format8(sensor_data[0:2])
        HMC_y = format8(sensor_data[2:4])
        HMC_z = format8(sensor_data[4:6])
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  HMC_x, HMC_y, HMC_z

#"HIH6130" "HIH6130"
    elif sensor_id == '11':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  format6(sensor_data[0:2]), format6(sensor_data[2:4])





# ######## Dark voltages of ADPS, MLX75305, TSL260 and TSL250s are needed to be measured!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#"APDS-9006-020" "APDS-9006-020"  480 - 6400 nm wave
    elif sensor_id == '12':        
        APDS_voltage = calc_input_voltage(format1(sensor_data))
        APDS_lux = APDS_irrad(APDS_voltage)
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        # print "{:8.6f}".format(APDS_voltage), 
        print "{:5.2f}".format(format1(sensor_data)), "{:5.2f}".format(APDS_lux)

######## Dark voltages of ADPS, MLX75305, TSL260 and TSL250s are needed to be measured!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#"TSL260RD" "TSL260RD"  940 nm wave
    elif sensor_id == '13':
        TSL260RD_voltage = calc_input_voltage(format1(sensor_data))
        TSL260RD_val = TSL260_irrad(TSL260RD_voltage)
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        # print "{:9.8f}".format(TSL260RD_voltage), 
        print "{:5.2f}".format(format1(sensor_data)), "{:5.2f}".format(TSL260RD_val)

######## Dark voltages of ADPS, MLX75305, TSL260 and TSL250s are needed to be measured!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#"TSL250RD" "TSL250RD" 640 nm wave
    elif sensor_id == '14':
        TSL250RD_2_voltage = calc_input_voltage(format1(sensor_data))
        TSL250RD_2_val = TSL250_irrad(TSL250RD_2_voltage)
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        # print "{:10.9f}".format(TSL250RD_2_voltage),
        print format1(sensor_data), "{:5.2f}".format(TSL250RD_2_voltage), "{:5.2f}".format(TSL250RD_2_val)

######## Dark voltages of ADPS, MLX75305, TSL260 and TSL250s are needed to be measured!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#"MLX75305" "MLX75305" 500 - 1000 nm wave
    elif sensor_id == '15':
        MLX75305_voltage = calc_input_voltage(format1(sensor_data))
        MLX75305_val = (MLX75305_voltage - 0.09234) / 0.007   #with gain 1, the factor is 7mA/(uW/cm^2)
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        # print "{:8.6f}".format(MLX75305_voltage),
        print "{:5.2f}".format(format1(sensor_data)), "{:5.2f}".format(MLX75305_val)

######## Offset term related to climate, geographic condition!!!!!!!!!!!!!!!!!!!!!
#"ML8511" "ML8511"  typically 365 nm wave (300 - 380 nm wave)
    elif sensor_id == '16':
        ML8511_voltage = calc_input_voltage(format1(sensor_data))

        # ML8511_val = ML8511_voltage * 12.49 - 14.735
        # ML8511_val = ML8511_voltage * 12.49 - 17.72
        #### voltage difference btw dark/10,000 mW/m^2: 1.2V --> 0.12
        #### subtranct 1.49916 / 0.12 - dark diff (cf. datasheet)
        ML8511_val = (ML8511_voltage - 1) * 14.9916 / 0.12 - 18.71

        if 2.5 <= ML8511_val <= 3.0:
            ML8511_val = ML8511_val - 0.3
        elif 3.0 <= ML8511_val <= 4.0:
            ML8511_val = ML8511_val - 0.6
        elif 4.0 <= ML8511_val <= 4.2:
            ML8511_val = ML8511_val - 0.4
        elif 4.5 < ML8511_val:
            ML8511_val = ML8511_val + 0.25

        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print "{:5.2f}".format(format1(sensor_data)), "{:5.2f}".format(ML8511_val)


# # "D6T" has been removed
#     elif sensor_id == '17':
#         print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
#         data = ''
#         for i in xrange(len(sensor_data)/2):
#             data = data + str(format6(sensor_data[2*i:2*(i+1)])) + ' '
#         print  data
# # "MLX90614" "MLX90614"
#     elif sensor_id == '18':
#         print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
#         print  format6(sensor_data)


#"TMP421" "TMP421"
    elif sensor_id == '19':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  format6(sensor_data)


# "SPV1840LR5H-B" has been removed
    elif sensor_id == '20':
        SPV_2_OUT = (format1(sensor_data) / 32768.0000) * 2.048
        SPV_2_voltage = SPV_2_OUT * 5.00 / 2.00
        SPV_2_val = -20 * numpy.log10(SPV_2_voltage/3.3)
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  "{:2.6f}".format(SPV_2_val)


#"Total reducing gases" "Total reducing gases"
    elif sensor_id == '21':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print str(format5(sensor_data))
#"Ethanol (C2H5-OH)" has been removed
    #elif sensor_id == '22':
        #print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        #print str(format5(sensor_data))
#"Nitrogen Di-oxide (NO2)" "Nitrogen Di-oxide (NO2)"
    elif sensor_id == '23':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  str(format5(sensor_data))
#"Ozone (03)" "Ozone (03)"
    elif sensor_id == '24':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  str(format5(sensor_data))
#"Hydrogen Sulphide (H2S)" "Hydrogen Sulphide (H2S)"
    elif sensor_id == '25': #sensor id 0x19
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  str(format5(sensor_data))
#"Total Oxidizing gases" "Total Oxidizing gases"
    elif sensor_id == '26':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  str(format5(sensor_data))
#"Carbon Monoxide (C0)" "Carbon Monoxide (C0)"
    elif sensor_id == '27':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  str(format5(sensor_data))
#"Sulfur Dioxide (SO2)" "Sulfur Dioxide (SO2)"
    elif sensor_id == '28':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  str(format5(sensor_data))


#"SHT25" "SHT25"
    elif sensor_id == '29':
        SHT_temperature = format2(sensor_data[0:2]) / 100.00
        SHT_humidity = format1(sensor_data[2:4]) / 100.00
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  SHT_temperature, SHT_humidity
#"LPS25H" "LPS25H"
    elif sensor_id == '30':
        LPS_temperature = format2(sensor_data[0:2]) / 100.00
        LPS_pressure = format4(sensor_data[2:5])
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  LPS_temperature, LPS_pressure
#"Si1145" "Si1145"
    elif sensor_id == '31':
        print "Sensor:", sensor_id, sensor_list[int(sensor_id)],'@ ',
        print  hex(format1(sensor_data[0:2])),hex(format2(sensor_data[2:4])),hex(format2(sensor_data[4:6]))

#"Intel MAC" "Intel MAC"
    elif sensor_id == '32': # sensor id 0x20
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        data = ''
        for i in range(len(sensor_data)):
            data = data + str(format3(sensor_data[i]))
        print  data

#"CO ADC temp"
    elif sensor_id == '33':
        sensor33_val = format2(sensor_data) / 100.00
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  sensor33_val
#"IAQ/IRR ADC temp"
    elif sensor_id == '34':
        sensor34_val = format2(sensor_data) / 100.00
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  sensor34_val
#"O3/NO2 ADC temp"
    elif sensor_id == '35':
        sensor35_val = format2(sensor_data) / 100.00
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  sensor35_val
#"SO2/H2S ADC temp"
    elif sensor_id == '36':
        sensor36_val = format2(sensor_data) / 100.00
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  sensor36_val
#"CO LMP temp"
    elif sensor_id == '37':
        sensor37_val = format2(sensor_data) / 100.00
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  sensor37_val
#"Accelerometer"
    elif sensor_id == '38':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  format2(sensor_data[0:2]),format2(sensor_data[2:4]),format2(sensor_data[4:6]),format4(sensor_data[6:9])
#"Gyroscope"
    elif sensor_id == '39':
        print "Sensor:", sensor_id,sensor_list[int(sensor_id)],'@ ',
        print  format2(sensor_data[0:2]),format2(sensor_data[2:4]),format2(sensor_data[4:6]),format4(sensor_data[6:9])

#"HDC1010"
    elif sensor_id == '53':
        print "Sensor: 53 HDC1010 Temp & RH @ ",
        HDC_temperature = format2(sensor_data[0:2]) / 100.00
        HDC_humidity = format1(sensor_data[2:4]) / 100.00
        print  HDC_temperature, HDC_humidity


class usbSerial ( threading.Thread ):


    def __init__ ( self,port):
        self.port = port
        threading.Thread.__init__ ( self )
        self.lastSeq = 0
        self.currentSeq = 0
        self.repeatInt = 0.01
        self.data = []
        self.CoreSenseConf = 1
        self.dataLenBit = 0
        self.packetmismatch = 0
        self.keepAlive = 1

        # self.failCount = 0
        # self.file = open('failed.txt', 'w+')
        # self.cumulativeCount = 0
        # self.failBuffer = Queue.Queue()

    def run (self):
        print time.asctime()
        #Checking if the port is still available for connection
        try:
            self.ser = serial.Serial(self.port, baudrate=115200, timeout=0)
        except:
            #port unavalable. Between Inotify spanning the thread and the current
            #read the port has magically disappeared.
            self.keepAlive = 0
            self.stop()

        print "> > >  usbSerial initiated on port"+str(self.port)+" @ "+str(time.asctime())
        self.counter = 0

        try:
            self.ser.flushInput()
            self.ser.flushOutput()
        except:
            self.stop()

        while self.keepAlive:
            time.sleep(self.repeatInt)
            streamData = ''
            try:
                self.counter = self.counter + 1
                if self.ser.inWaiting() > 0:
                    streamData = self.ser.read(self.ser.inWaiting())
                    self.counter = 0
            except:
                print "Serial port connection lost."
                self.stop()

            if streamData <> '':
                self.marshalData(streamData)

            if (self.counter > 100000 or self.packetmismatch > 10) and (self.CoreSenseConf):
                print "not blade - error - " + str(self.counter) + " and " + str(self.packetmismatch)
                self.stop()

        print "< < <  usbSerial exit - port"+str(self.port)+" @ "+str(time.asctime())
        print ""


    def stop (self):
        self.keepAlive = False
        try :
            self.ser.close()
            self.file.close()
        except:
            pass


    def marshalData(self,_dataNew):
        self.data.extend(_dataNew)
        bufferLength = len(self.data)
        while self.keepAlive:

            try:
                #lock header
                del self.data[:self.data.index(_preamble)]
                _preambleLoc = 0
                bufferLength = len(self.data)
            except:
                #no header found, we ended up purging the data
                del self.data[:bufferLength]
                break

            if (len(self.data) < 4):
                #not enough data for a legal packet, we have to wait...
                break
            else:
                if ((ord(self.data[_preambleLoc+_protVerFieldDelta]) & 0x0f) <> 0):

                    #we have a packet of version we do not understand - either wrong version or
                    #we have a wrong byte as the header. We will delete a byte and try header lock again.
                    del self.data[0]

                else:
                    _msg_seq_num = (ord(self.data[_preambleLoc+_protVerFieldDelta]) & 0xf0) >> 4

                    #it is protocol version 0, and we can parse that data, using this script.

                    _postscriptLoc = ord(self.data[_preambleLoc+_datLenFieldDelta]) + _msgPSDelta + _datLenFieldDelta
                    if (_postscriptLoc > _maxPacketSize):
                        #the packet size if huge, it is unlikely that we have cuaght the header, so consume a
                        #byte.
                        del self.data[0]

                    else:
                        if (_postscriptLoc >= bufferLength):
                        #We do not have full packet in the buffer, cannot process.
                            break
                        else:
                            try:
                                if self.data[_postscriptLoc] <> _postScript:
                                    #we probably have not locked to the header, consume and retry locking to header
                                    del self.data[0]
                                else:
                                    #we may have a valid packet
                                    _packetCRC = 0
                                    packetmismatch = 0

                                    for i in range(_preambleLoc + _datLenFieldDelta + 0x01, _postscriptLoc):
                                        #print hex(ord(self.data[i])),
                                        _packetCRC = ord(self.data[i]) ^ _packetCRC
                                        for j in range(8):
                                            if (_packetCRC & 0x01):
                                                _packetCRC = (_packetCRC >> 0x01) ^ 0x8C
                                            else:
                                                _packetCRC =  _packetCRC >> 0x01
                                    print ''
                                    if _packetCRC <> 0x00:
                                        #bad packet or we probably have not locked to the header, consume and retry locking to header
                                        #ideally we should be able to throw the whole packet out, but purging just a byte for avoiding corner cases.
                                        del self.data[0]
                                    else:
                                        #print self.data, ord(self.data[_postscriptLoc])
                                        print '-------------'
                                        #print time.asctime(), _msg_seq_num, _postscriptLoc
                                        
                                        # # SH put data into buffer to store into a file
                                        # try:
                                        #     self.failBuffer.put(self.data[0:_postscriptLoc])
                                        #     if self.failBuffer.qsize() > 20:
                                        #         if self.failCount > 0:
                                        #             self.file.write(self.failBuffer.get())
                                        #             self.file.write("\r\n")
                                        #             self.failCount = self.failCount - 1
                                        #         else:
                                        #             self.failBuffer.get()
                                        # except:
                                        #     print "Error while writing file"
                                        #     print "failcount was ", self.failCount
                                        #     pass

                                        #extract the data bytes alone, exclude preamble, prot version, len, crc and postScript
                                        extractedData = self.data[_preambleLoc+3:_postscriptLoc-1]
                                        consume_ptr = 0x00
                                        self.CoreSenseConf = 0

                                        del self.data[:self.data.index(_postScript)+1]

                                        #print ":".join("{:02x}".format(ord(c)) for c in extractedData)

                                        while consume_ptr < len(extractedData):

                                            try:
                                                This_id = str(ord(extractedData[consume_ptr]))
                                                This_id_msg_size_valid = ord(extractedData [consume_ptr+1])
                                                This_id_msg_size = This_id_msg_size_valid & 0x7F
                                                #print This_id_msg_size
                                                This_id_msg_valid = (This_id_msg_size_valid & 0x80) >> 7
                                                This_id_msg = extractedData[consume_ptr+2:consume_ptr+2+This_id_msg_size]
                                                
                                            except Exception,e:
                                                print "ERROR!!!!"
                                                print str(e)
                                                print "consume_ptr: ", consume_ptr, " len(extractedData): ", len(extractedData)
                                                pass
                                            
                                            # if This_id == '16':
                                            #     if format1(This_id_msg) == 0xffff:
                                            #         # ERROR FOUND~!!!!!!!!!!!!!!!!!!!
                                            #         self.failCount = 20
                                            #         self.cumulativeCount = self.cumulativeCount + 1
                                            #         if self.cumulativeCount > 50:
                                            #             # I do not want to see any more.... Get me out of here!
                                            #             self.stop()
                                            #             break



                                            #print (int(This_id)), This_id_msg_valid, This_id_msg_size, This_id_msg
                                            
                                            consume_ptr = consume_ptr + 2 + This_id_msg_size
                                            if (This_id_msg_valid == 1):
                                                try:
                                                    print int(time.time()),
                                                    parse_sensor (This_id, This_id_msg)
                                                    pass
                                                except:
                                                    pass
                                            else:
                                                pass
                            except:
                                print "ERRor"
                                print "buffer len", bufferLength
                                print "data len", len(self.data)
                                print "_postscriptLoc", _postscriptLoc
                                del self.data[0]
                                pass
