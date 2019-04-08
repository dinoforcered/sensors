#!/usr/bin/env python3
# ANL:waggle-license
# This file is part of the Waggle Platform.  Please see the file
# LICENSE.waggle.txt for the legal details of the copyright and software
# license.  For more details on the Waggle project, visit:
#          http://www.wa8.gl
# ANL:waggle-license
from serial import Serial
import sys
import re

with Serial(sys.argv[1], baudrate=9600, timeout=5) as ser:
    while True:
        try:
            cmd = input('$ ')
            ser.write(cmd.encode())
            ser.write(b'\n')

            while True:
                line = ser.readline().decode()

                if len(line) == 0:
                    print('timeout')
                    break

                match = re.match('(ok|err|debug): (.*)', line)

                if match is None:
                    continue

                status, text = match.groups()

                if status == 'ok':
                    print(repr(text))
                    break

                print(match.group())

        except KeyboardInterrupt:
            break
