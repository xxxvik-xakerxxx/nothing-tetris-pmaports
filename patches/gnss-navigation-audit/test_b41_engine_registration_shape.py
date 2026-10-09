#!/usr/bin/env python3
"""Actual24-slot engine registration shape; retained global side effects offline."""
from pathlib import Path
import struct
import sys
from test_b41_startup import Machine, LIB_SHA, DATA, STOP

def verify(path):
    for missing in [None] + list(range(10)):
        m=Machine(path,LIB_SHA,[(0x52f9d0,0x52fbb0)])
        slots=[STOP+0x100+8*i if i!=missing else 0 for i in range(10)]+[0]*14
        m.u.mem_write(DATA,struct.pack("<24Q",*slots))
        m.run(0x52f9d0,args=(DATA,))
        required=missing is not None and bool(0x3fb & (1<<missing))
        assert m.args()[0]==(0xffffffff if required else 0)
        for slot,got in ((1,0x6e6800),(3,0x6e6d30),(4,0x6e6d28)):
            assert struct.unpack("<Q",m.u.mem_read(m.global_at(got),8))[0]==slots[slot]
    print("PASS: actual24-slot table with all14 optional NULL; mandatory0x3fb; failed calls retain globals")

if __name__=="__main__": verify(Path(sys.argv[1]))
