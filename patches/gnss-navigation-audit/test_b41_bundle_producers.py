#!/usr/bin/env python3
"""Pinned additional second-config26-byte producers, not synthetic engine calls."""
from pathlib import Path
import struct
import sys
from unicorn.arm64_const import UC_ARM64_REG_X10, UC_ARM64_REG_X22, UC_ARM64_REG_X25
from test_b41_startup import Machine, MNLD_SHA

def verify(path):
    def machine(ranges):
        m=Machine(path,MNLD_SHA,ranges);m.map(0xdd000,0x3000);m.map(0x9a000,4096);return m
    def put(m,address,value,width): m.u.mem_write(address,value.to_bytes(width,"little"))
    def read(m,offset,width): return int.from_bytes(m.u.mem_read(0xde590+offset,width),"little")
    for value in (0,0x12345678,0xffffffff):
        m=machine([(0x63b84,0x63ba8)])
        m.set(UC_ARM64_REG_X10,0xde5b4)
        put(m,0x88a5c,value,4);put(m,0x88c58,value^0x87654321,4)
        put(m,0x88c68,0x1122334455667788,8)
        m.run(0x63b84,0x63ba8)
        assert read(m,0x24,4)==value and read(m,0xb4,4)==value^0x87654321
        assert read(m,0xb8,8)==0x1122334455667788
        m=machine([(0x63920,0x63958)])
        m.set(UC_ARM64_REG_X22,0xde59c)
        put(m,0xde21c,value,4);put(m,0x88c18,0xab,1)
        m.mock(0x84f30,lambda a:0)
        m.run(0x63920,0x63958)
        assert read(m,0x64,4)==value and read(m,0x68,4)==(value+0x50000)&0xffffffff
        assert read(m,0x0c,1)==0xab
    for value in (0,1,255):
        m=machine([(0x56c90,0x56c9c),(0x63a84,0x63a88)])
        put(m,0x9a4eb,value,1);m.run(0x56c90)
        assert m.args()[0]==value
        m.set(UC_ARM64_REG_X25,0xde5a0)
        m.run(0x63a84,0x63a88,args=(value,))
        assert read(m,0xc4,1)==value
    print("PASS: second-config additional26 producer bytes; unsigned32 addition wrap preserved")

if __name__=="__main__": verify(Path(sys.argv[1]))
