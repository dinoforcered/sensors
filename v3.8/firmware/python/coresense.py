# ANL:waggle-license
# This file is part of the Waggle Platform.  Please see the file
# LICENSE.waggle.txt for the legal details of the copyright and software
# license.  For more details on the Waggle project, visit:
#          http://www.wa8.gl
# ANL:waggle-license
from serial import Serial
from contextlib import closing
import sys
import re
from datetime import datetime


class Coresense:

    def __init__(self, port):
        self.ser = Serial(port, baudrate=9600, timeout=10000)

    def close(self):
        self.ser.close()

    def puts(self, line):
        self.ser.write(line.strip().encode())
        self.ser.write(b'\n')

    def gets(self):
        return self.ser.readline().decode().strip()

    def expect(self, pattern):
        while True:
            line = self.gets()
            if re.match(pattern, line):
                return line

    def read_version(self):
        self.puts('ver')
        line = self.expect('ver')
        return line.split()[1]

    def read_id(self):
        self.puts('id')
        line = self.expect('id')
        return line.split()[1]

    def list_devices(self):
        self.puts('devices')
        self.expect('devices')

        devices = []

        while True:
            line = self.gets()
            if len(line) == 0:
                break
            devices.append(line)

        return devices

    def read_devices(self, devices):
        self.puts('read {}'.format(' '.join(devices)))
        self.expect('read')

        results = {}

        while True:
            line = self.gets()
            if len(line) == 0:
                break
            key, *values = line.split()
            results[key] = values

        return results

    def read_serial(self, port):
        self.puts('readser {}'.format(port))
        self.expect('readser')

        lines = []

        while True:
            line = self.gets()
            if len(line) == 0:
                break
            lines.append(line)

        return '\n'.join(lines)


if __name__ == '__main__':
    with closing(Coresense(sys.argv[1])) as cs:
        print('version', cs.read_version())
        print('id', cs.read_id())

        devices = cs.list_devices()
        print('devices', ', '.join(devices))

        while True:
            dt = datetime.now()
            results = cs.read_devices(devices)

            print('timestamp', dt.strftime('%Y/%m/%d %H:%M:%S'))

            for k, v in results.items():
                print(k, ' '.join(v))

            print()
