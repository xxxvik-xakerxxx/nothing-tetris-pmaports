#!/usr/bin/env python3
"""Pinned producer coverage, not a constructor or permission to enter libMNL."""
from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True)
class Field:
    offset: int
    width: int
    producer: str
    source: str
    missing: str | None = None


FIELDS = (
    Field(0x00, 4, "62bc8", "literal22b58: u32=1"),
    Field(0x04, 4, "62bc8", "literal22b58+4: u32=0"),
    Field(0x08, 4, "62d08", "u32=0"),
    Field(0x0c, 4, "62b8c", "initial zero, no later write identified"),
    Field(0x10, 2, "62be4", "u16=100"),
    Field(0x12, 1, "62b8c", "initial zero, no later write identified"),
    Field(0x13, 1, "62534", "clock selector after ioctl11/property_set",
          "successful ioctl11 and audited property-to-clock policy"),
    Field(0x14, 2, "62c50/62cd8/62cbc", "profile9bc3c+4 or default2000",
          "producer and applicability of de22c/profile9bc3c"),
    Field(0x16, 2, "62b8c", "initial zero, no later write identified"),
    Field(0x18, 4, "62c48/62cdc/624f4", "profile9bc3c or default26000000; clock flag81 overrides52000000",
          "successful clock ioctl11 and explicit platform profile selection"),
    Field(0x1c, 4, "62bd8", "u32=115200"),
    Field(0x20, 4, "62d04", "88794==0 ? 200 : 1000",
          "complete producer/meaning of global88794"),
    Field(0x24, 1, "62cd4/62c54", "profile9bc3c+9 or default0",
          "profile selection and source"),
    Field(0x25, 3, "62b9c", "initial zero, no later write identified"),
    Field(0x28, 4, "63370/634bc", "de308 OR selected2323c flags",
          "de308 producer and selected global88c1c mode"),
    Field(0x2c, 4, "63390", "conditional secondary de308",
          "secondary receiver identity/helper56ce0"),
    Field(0x30, 4, "6336c", "de304",
          "de304 producer/policy"),
    Field(0x34, 4, "6338c", "conditional secondary de304",
          "secondary receiver policy"),
    Field(0x38, 4, "6350c/63528", "88e14 override/default88c20 or conditional4",
          "88e10/88e14 origins and helper62a20 policy"),
    Field(0x3c, 16, "56d00..57184/62c00/62cac", "de490 calibration or selected profile9bc48",
          "same-unit complete16-byte ML4A/EL6N read with actual chip-string selection; modern property branch/profile override unresolved"),
    Field(0x4c, 4, "62ba0", "initial zero, no later write identified"),
    Field(0x50, 1, "63b80", "de9d8, values>1 normalized0",
          "de9d8 producer/policy"),
    Field(0x51, 3, "62ba0", "initial zero, no later write identified"),
    Field(0x54, 4, "63498", "ioctl16 output, even if ioctl failed",
          "successful LNA-pin ioctl16 or legitimate alternate contract"),
    Field(0x58, 3, "62ba0", "initial zero, no later write identified"),
    Field(0x5b, 1, "63a30", "de228/88794/4eee0/88c4c conditional",
          "MPE policy producer and backend state"),
    Field(0x5c, 8, "62ba0", "initial zero, no later write identified"),
    Field(0x64, 4, "5dd10/5dd70/5dd60", "ioctl21 or override88c74; failure=-1",
          "modem-status ioctl21 contract/ownership, not a guessed register"),
    Field(0x68, 4, "62ffc/63020", "offload1 versus host0",
          "transport ownership and selected88c78 path"),
    Field(0x6c, 1, "63a88", "ddd84 ? 88c80 : 0",
          "feature-byte policy producers"),
    Field(0x6d, 3, "62ba4", "initial zero, no later write identified"),
)


def report():
    covered = [0] * 0x70
    for field in FIELDS:
        for index in range(field.offset, field.offset + field.width):
            covered[index] += 1
    if covered != [1] * 0x70:
        raise ValueError("first-config field map overlaps or leaves holes")
    return {
        "size": 0x70,
        "constructor_ready": False,
        "missing_inputs": [field.missing for field in FIELDS if field.missing],
        "fields": [asdict(field) for field in FIELDS],
        "config_xml_paths": ["/data/vendor/gps/MNL_Config.xml", "/vendor/etc/MNL_Config.xml"],
        "config_xml_contract": "mtk_gps_get_MNL_Config_XML_param; output0xfc4; verified file/default policy required",
        "transport": {
            "host": "__open_2(global88a80,O_RDWR) -> global88798; secondary8879c conditional",
            "offload": "mtk_gps_mnl_ofl_mcu2ap_device_open and fd_by_port; first+0x68=1",
            "second_config_fds": "0x10 primary88798, 0x14 secondary8879c",
            "clock_frequency": "ioctl30 return selector0=26MHz/1=52MHz, not Hz or output pointer; AGPS131 payload",
            "stop": "close paths exist; complete libMNL stop/descriptor owner contract unresolved",
        },
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
