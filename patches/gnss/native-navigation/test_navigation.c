/* SPDX-License-Identifier: GPL-2.0-only */
#include "navigation.h"
#include <assert.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void put16(uint8_t *p, uint16_t v) { p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static void put32(uint8_t *p, uint32_t v)
{ for (unsigned i=0;i<4;++i) p[i]=(uint8_t)(v>>(8u*i)); }
static void put_double(uint8_t *p, double v)
{
    uint64_t bits; memcpy(&bits,&v,sizeof(bits));
    for (unsigned i=0;i<8;++i) p[i]=(uint8_t)(bits>>(8u*i));
}
static uint32_t read32(const uint8_t *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }

/* Fixture-only wire producer; no firmware, I/O or vendor function execution. */
static size_t frame(uint8_t command, const uint8_t *payload, uint16_t n, uint8_t high, uint8_t *out)
{
    uint8_t body[B41_NAV_PAYLOAD_MAX+6u]; uint32_t sum=0; size_t size=2;
    assert(n<=B41_NAV_PAYLOAD_MAX && high<16);
    put16(body,(uint16_t)((n+4u)|((uint32_t)high<<12)));
    body[2]=command; body[3]=0xfe; memcpy(body+4,payload,n);
    for (unsigned i=0;i<(unsigned)n+4u;++i) sum+=body[i];
    put16(body+4u+n,(uint16_t)sum);
    out[0]=0xaa; out[1]=0xf0;
    for (unsigned i=0;i<(unsigned)n+6u;++i) {
        if (body[i]==0xaa || body[i]==0xde) {
            out[size++]=0xde; out[size++]=body[i]==0xaa ? 0xdf : 0xe0;
        } else out[size++]=body[i];
    }
    out[size++]=0xaa; out[size++]=0x0f;
    return size;
}
static struct b41_nav_packet packet(uint8_t command, unsigned size)
{
    struct b41_nav_packet result={0};
    assert(size<=B41_NAV_PAYLOAD_MAX);
    result.command=command; result.payload_size=(uint16_t)size;
    for (unsigned i=0;i<size;++i) result.payload[i]=(uint8_t)i;
    return result;
}
static void test_wire(void)
{
    uint8_t wire[B41_NAV_WIRE_MAX], payload[B41_NAV_PAYLOAD_MAX];
    struct b41_nav_packet out, before;
    for (unsigned i=0;i<sizeof(payload);++i) payload[i]=(uint8_t)i;
    size_t size=frame(0x41,payload,32,9,wire);
    assert(b41_nav_packet_decode(wire,size,&out)==0);
    assert(out.command==0x41 && out.length_high_nibble==9 && out.payload_size==32);
    assert(!memcmp(out.payload,payload,32));
    size=frame(0x60,payload,B41_NAV_PAYLOAD_MAX,15,wire);
    assert(b41_nav_packet_decode(wire,size,&out)==0);
    assert(!memcmp(out.payload,payload,sizeof(payload)));
    before=out;
    wire[size-1]^=1;
    assert(b41_nav_packet_decode(wire,size,&out)==-EPROTO && !memcmp(&out,&before,sizeof(out)));
    size=frame(0x41,payload,32,0,wire); wire[6]^=1;
    assert(b41_nav_packet_decode(wire,size,&out)==-EBADMSG && !memcmp(&out,&before,sizeof(out)));
    size=frame(0x41,payload,32,0,wire); wire[6]=0xaa;
    assert(b41_nav_packet_decode(wire,size,&out)==-EPROTO);
    wire[6]=0xde; wire[7]=0xdd;
    assert(b41_nav_packet_decode(wire,size,&out)==-EPROTO);
    size=frame(0x41,payload,32,0,wire); wire[5]=0xfd;
    assert(b41_nav_packet_decode(wire,size,&out)==-EPROTO);
    assert(b41_nav_packet_decode(wire,9,&out)==-EMSGSIZE);
    assert(b41_nav_packet_decode(wire,B41_NAV_WIRE_MAX+1u,&out)==-EMSGSIZE);
    assert(b41_nav_packet_decode(NULL,0,&out)==-EINVAL);
    assert(b41_nav_packet_decode(wire,size,NULL)==-EINVAL);
}
static struct b41_nav_epoch_owner begin(void)
{
    struct b41_nav_epoch_owner owner={0}; struct b41_nav_epoch untouched;
    struct b41_nav_packet header=packet(0x2c,66);
    assert(b41_nav_epoch_init(&owner,10,10000)==0);
    assert(b41_nav_epoch_init(&owner,10,20000)==-EALREADY);
    assert(b41_nav_epoch_accept(&owner,&header,11,&untouched)==0);
    return owner;
}
static void test_epochs(void)
{
    struct b41_nav_epoch_owner owner=begin(); struct b41_nav_epoch out, before;
    struct b41_nav_packet one=packet(0x41,32), two=packet(0x4d,47), end=packet(0x4c,10);
    memset(&out,0xa5,sizeof(out)); before=out;
    assert(b41_nav_epoch_accept(&owner,&one,12,&out)==0 && !memcmp(&out,&before,sizeof(out)));
    assert(b41_nav_epoch_accept(&owner,&two,13,&out)==0);
    assert(b41_nav_epoch_accept(&owner,&end,14,&out)==1);
    assert(out.count==2 && out.begin_ns==11 && out.end_ns==14);
    assert(out.header_word0==0x01000302u && out.header_word4==0x05040706u);
    assert(out.header_field8_9_44==((8u<<2)|(9u<<10)));
    assert(out.records[0].command==0x41 && out.records[0].index==0);
    assert(out.records[0].decoded.fe41.words[0]==0x06070405u);
    assert(out.records[0].decoded.fe41.words[6]==0x1e1f1c1du);
    assert(out.records[1].index==1 && out.records[1].decoded.fe4d.prefix24==0x00000201u);
    assert(out.records[1].decoded.fe4d.words[0]==0x08070a09u);
    assert(out.records[1].decoded.fe4d.words[9]==0x2c2b2e2du);
    assert(out.end.word1==0x02010403u && out.end.word5==0x06050807u);
    assert(out.end.byte0==0 && out.end.byte9==9);
    /* Twenty4D records are permitted; limits are shared across record types. */
    static const uint8_t commands[7]={0x2b,0x3b,0x41,0x4b,0x4d,0x5c,0x91};
    static const unsigned lengths[7]={46,14,32,47,47,113,115}, maximum[7]={11,12,11,15,20,17,11};
    for (unsigned kind=0;kind<7;++kind) {
        owner=begin(); one=packet(commands[kind],lengths[kind]);
        for (unsigned i=0;i<maximum[kind];++i) assert(b41_nav_epoch_accept(&owner,&one,12u+i,&out)==0);
        before=out;
        assert(b41_nav_epoch_accept(&owner,&one,50,&out)==-EOVERFLOW);
        assert(!memcmp(&out,&before,sizeof(out)));
        assert(b41_nav_epoch_accept(&owner,&end,51,&out)==-EOVERFLOW);
        assert(b41_nav_epoch_init(&owner,60,20000)==-EOVERFLOW);
    }
    owner=begin(); one=packet(0x4d,47); two=packet(0x41,32);
    for (unsigned i=0;i<11;++i) assert(b41_nav_epoch_accept(&owner,&one,12u+i,&out)==0);
    assert(b41_nav_epoch_accept(&owner,&two,30,&out)==-EOVERFLOW);
    owner=begin(); one=packet(0x41,31);
    assert(b41_nav_epoch_accept(&owner,&one,12,&out)==-EMSGSIZE);
    owner=begin(); assert(b41_nav_epoch_accept(&owner,&end,10000,&out)==-ETIMEDOUT);
    owner=begin(); assert(b41_nav_epoch_accept(&owner,&end,10,&out)==-ESTALE);
    owner=begin(); one=packet(0x31,4);
    assert(b41_nav_epoch_accept(&owner,&one,12,&out)==-EOPNOTSUPP);
    owner=begin(); one=packet(0x2c,66);
    assert(b41_nav_epoch_accept(&owner,&one,12,&out)==-EPROTO);
    owner=(struct b41_nav_epoch_owner){0};
    assert(b41_nav_epoch_init(&owner,10,10000)==0);
    assert(b41_nav_epoch_accept(&owner,&end,11,&out)==-EPROTO);
}
static void test_init_and_time(void)
{
    uint8_t wire[32], message[B41_NAV_TIME_MESSAGE_SIZE], before[B41_NAV_TIME_MESSAGE_SIZE];
    struct b41_nav_packet decoded;
    size_t written=999;
    memset(wire,0xa5,sizeof(wire));
    assert(b41_nav_post_init_reporting_encode(wire,14,&written)==-ENOSPC && written==999 && wire[0]==0xa5);
    assert(b41_nav_post_init_reporting_encode(wire,sizeof(wire),&written)==0 && written==15);
    assert(b41_nav_packet_decode(wire,written,&decoded)==0 && decoded.command==5 && decoded.payload_size==5);
    assert(!memcmp(decoded.payload,"\x32\0\0\x01\0",5));
    struct b41_nav_utc_sample sample={315964800000u,100,20,18};
    struct b41_nav_time_seed seed, old;
    assert(b41_nav_time_seed_build(&sample,250000100u,1000000000u,&seed)==0);
    assert(seed.gps_week==0 && seed.tow_seconds==18.25 && seed.uncertainty_ms==270.0f);
    memset(message,0xa5,sizeof(message)); memcpy(before,message,sizeof(message));
    assert(b41_nav_time_message_encode(&seed,message,sizeof(message)-1)==-ENOSPC);
    assert(!memcmp(message,before,sizeof(message)));
    assert(b41_nav_time_message_encode(&seed,message,sizeof(message))==0);
    assert(read32(message)==0x00e803f8u && read32(message+4)==8);
    assert(message[0x8c]==0 && message[0x8d]==0 && read32(message+0x9c)==0x43870000u);
    uint8_t expected[8]; put_double(expected,18.25);
    assert(!memcmp(message+0x94,expected,8));
    for (unsigned i=8;i<0x8c;++i) assert(message[i]==0);
    old=seed;
    assert(b41_nav_time_seed_build(&sample,99,1000,&seed)==-ESTALE && !memcmp(&seed,&old,sizeof(seed)));
    assert(b41_nav_time_seed_build(&sample,1000,1000,&seed)==-ETIMEDOUT);
    sample.unix_ms=UINT64_MAX;
    assert(b41_nav_time_seed_build(&sample,100,1000,&seed)==-EOVERFLOW);
    sample.unix_ms=315964799999u;
    assert(b41_nav_time_seed_build(&sample,100,1000,&seed)==-ERANGE);
    sample.unix_ms=315964800000u; sample.uncertainty_ms=0;
    assert(b41_nav_time_seed_build(&sample,100,1000,&seed)==-EINVAL);
    seed=old; seed.tow_seconds=NAN;
    assert(b41_nav_time_message_encode(&seed,message,sizeof(message))==-EINVAL);
    seed=old; seed.tow_seconds=604800;
    assert(b41_nav_time_message_encode(&seed,message,sizeof(message))==-EINVAL);
    seed=old; seed.uncertainty_ms=-1;
    assert(b41_nav_time_message_encode(&seed,message,sizeof(message))==-EINVAL);
    sample=(struct b41_nav_utc_sample){316569600000u,10,1,0};
    assert(b41_nav_time_seed_build(&sample,10,100,&seed)==0 && seed.gps_week==1 && seed.tow_seconds==0);
}
static void position_record(uint8_t *p)
{
    memset(p,0,B41_NAV_POSITION_SIZE); put32(p,0x0c600000u);
    put16(p+4,80); p[6]=0; p[7]=6; /* Synthetic public GPS epoch: 1980-01-06. */
    put16(p+0x10,18); put32(p+0x14,18); p[0x18]=1; p[0x19]=3;
    put_double(p+0x30,12.25); put_double(p+0x38,-55.5); put_double(p+0x40,123.0);
}
static void test_position(void)
{
    uint8_t record[B41_NAV_POSITION_SIZE]; struct b41_nav_host_position out, before;
    position_record(record);
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==0);
    assert(out.state==B41_NAV_POSITION_3D && out.year==1980 && out.month==1 && out.day==6);
    assert(out.utc_correction_seconds==18 && out.gps_week==0 && out.gps_tow_seconds==18);
    assert(out.latitude_degrees==12.25 && out.longitude_degrees==-55.5 && out.altitude==123);
    before=out; record[4]=81;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-EPROTO && !memcmp(&out,&before,sizeof(out)));
    position_record(record); put_double(record+0x30,NAN);
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-ERANGE);
    position_record(record); put_double(record+0x38,180.001);
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-ERANGE);
    position_record(record); put_double(record+0x40,INFINITY);
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-ERANGE);
    record[0x19]=2;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==0 && out.state==B41_NAV_POSITION_2D && out.altitude==0);
    record[0x19]=1; record[0x30]=0xff; record[7]=0;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==0 && out.state==B41_NAV_POSITION_NOT_VALID);
    record[0x19]=0xff;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==0 && out.state==B41_NAV_POSITION_NOT_VALID);
    record[0x19]=0;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-EPROTO);
    position_record(record); record[0x18]=0;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==0 && out.state==B41_NAV_POSITION_NOT_VALID);
    position_record(record); record[0x18]=255;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-EOPNOTSUPP);
    position_record(record); put32(record+0x50,0x44010000u); put_double(record+0x40,18271);
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-ERANGE);
    position_record(record); record[6]=12;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-ERANGE);
    position_record(record); record[7]=32;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-ERANGE);
    position_record(record); record[0]=1;
    assert(b41_nav_host_position_decode(record,sizeof(record),&out)==-EPROTO);
    assert(b41_nav_host_position_decode(record,32,&out)==-EMSGSIZE);
}
int main(void)
{
    test_wire(); test_epochs(); test_init_and_time(); test_position();
    puts("PASS: synthetic typed navigation fixtures; no engine, fd, firmware or fix execution");
    return 0;
}
