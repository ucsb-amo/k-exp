# Autogenerated for the ucsb5master variant
core_addr = "192.168.1.75"

device_db = {
    "core": {
        "type": "local",
        "module": "artiq.coredevice.core",
        "class": "Core",
        "arguments": {"host": core_addr, "ref_period": 1e-09, "target": "rv32g"},
    },
    "core_log": {
        "type": "controller",
        "host": "::1",
        "port": 1068,
        "command": "aqctl_corelog -p {port} --bind {bind} " + core_addr
    },
    "core_moninj": {
        "type": "controller",
        "host": "::1",
        "port_proxy": 1383,
        "port": 1384,
        "command": "aqctl_moninj_proxy --port-proxy {port_proxy} --port-control {port} --bind {bind} " + core_addr
    },
    "core_cache": {
        "type": "local",
        "module": "artiq.coredevice.cache",
        "class": "CoreCache"
    },
    "core_dma": {
        "type": "local",
        "module": "artiq.coredevice.dma",
        "class": "CoreDMA"
    },

    "i2c_switch0": {
        "type": "local",
        "module": "artiq.coredevice.i2c",
        "class": "I2CSwitch",
        "arguments": {"address": 0xe0}
    },
    "i2c_switch1": {
        "type": "local",
        "module": "artiq.coredevice.i2c",
        "class": "I2CSwitch",
        "arguments": {"address": 0xe2}
    },
}

# master peripherals

device_db["grabber0"] = {
    "type": "local",
    "module": "artiq.coredevice.grabber",
    "class": "Grabber",
    "arguments": {"channel_base": 0x000000}
}

device_db["ttl0"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLInOut",
    "arguments": {"channel": 0x000002},
}

device_db["ttl1"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLInOut",
    "arguments": {"channel": 0x000003},
}

device_db["ttl2"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLInOut",
    "arguments": {"channel": 0x000004},
}

device_db["ttl3"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLInOut",
    "arguments": {"channel": 0x000005},
}

device_db["ttl4"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000006},
}

device_db["ttl5"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000007},
}

device_db["ttl6"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000008},
}

device_db["ttl7"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000009},
}

device_db["ttl8"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00000a},
}

device_db["ttl9"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00000b},
}

device_db["ttl10"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00000c},
}

device_db["ttl11"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00000d},
}

device_db["ttl12"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00000e},
}

device_db["ttl13"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00000f},
}

device_db["ttl14"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000010},
}

device_db["ttl15"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000011},
}

device_db["ttl16"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000012},
}

device_db["ttl17"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000013},
}

device_db["ttl18"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000014},
}

device_db["ttl19"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000015},
}

device_db["ttl20"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000016},
}

device_db["ttl21"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000017},
}

device_db["ttl22"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000018},
}

device_db["ttl23"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000019},
}

device_db["spi_zotino0"] = {
    "type": "local",
    "module": "artiq.coredevice.spi2",
    "class": "SPIMaster",
    "arguments": {"channel": 0x00001a}
}
device_db["ttl_zotino0_ldac"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00001b}
}
device_db["ttl_zotino0_clr"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00001c}
}
device_db["zotino0"] = {
    "type": "local",
    "module": "artiq.coredevice.zotino",
    "class": "Zotino",
    "arguments": {
        "spi_device": "spi_zotino0",
        "ldac_device": "ttl_zotino0_ldac",
        "clr_device": "ttl_zotino0_clr"
    }
}

device_db["eeprom_urukul0"] = {
    "type": "local",
    "module": "artiq.coredevice.kasli_i2c",
    "class": "KasliEEPROM",
    "arguments": {"port": "EEM6"}
}

device_db["spi_urukul0"] = {
    "type": "local",
    "module": "artiq.coredevice.spi2",
    "class": "SPIMaster",
    "arguments": {"channel": 0x00001d}
}

device_db["ttl_urukul0_io_update"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00001e}
}

device_db["ttl_urukul0_sw0"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00001f}
}

device_db["ttl_urukul0_sw1"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000020}
}

device_db["ttl_urukul0_sw2"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000021}
}

device_db["ttl_urukul0_sw3"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000022}
}

device_db["urukul0_cpld"] = {
    "type": "local",
    "module": "artiq.coredevice.urukul",
    "class": "CPLD",
    "arguments": {
        "spi_device": "spi_urukul0",
        "sync_device": None,
        "io_update_device": "ttl_urukul0_io_update",
        "refclk": 125000000.0,
        "clk_sel": 2
    }
}

device_db["urukul0_ch0"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 4,
        "cpld_device": "urukul0_cpld",
        "sw_device": "ttl_urukul0_sw0"
    }
}

device_db["urukul0_ch1"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 5,
        "cpld_device": "urukul0_cpld",
        "sw_device": "ttl_urukul0_sw1"
    }
}

device_db["urukul0_ch2"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 6,
        "cpld_device": "urukul0_cpld",
        "sw_device": "ttl_urukul0_sw2"
    }
}

device_db["urukul0_ch3"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 7,
        "cpld_device": "urukul0_cpld",
        "sw_device": "ttl_urukul0_sw3"
    }
}

device_db["eeprom_urukul1"] = {
    "type": "local",
    "module": "artiq.coredevice.kasli_i2c",
    "class": "KasliEEPROM",
    "arguments": {"port": "EEM8"}
}

device_db["spi_urukul1"] = {
    "type": "local",
    "module": "artiq.coredevice.spi2",
    "class": "SPIMaster",
    "arguments": {"channel": 0x000023}
}

device_db["ttl_urukul1_io_update"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000024}
}

device_db["ttl_urukul1_sw0"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000025}
}

device_db["ttl_urukul1_sw1"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000026}
}

device_db["ttl_urukul1_sw2"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000027}
}

device_db["ttl_urukul1_sw3"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x000028}
}

device_db["urukul1_cpld"] = {
    "type": "local",
    "module": "artiq.coredevice.urukul",
    "class": "CPLD",
    "arguments": {
        "spi_device": "spi_urukul1",
        "sync_device": None,
        "io_update_device": "ttl_urukul1_io_update",
        "refclk": 125000000.0,
        "clk_sel": 2
    }
}

device_db["urukul1_ch0"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 4,
        "cpld_device": "urukul1_cpld",
        "sw_device": "ttl_urukul1_sw0"
    }
}

device_db["urukul1_ch1"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 5,
        "cpld_device": "urukul1_cpld",
        "sw_device": "ttl_urukul1_sw1"
    }
}

device_db["urukul1_ch2"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 6,
        "cpld_device": "urukul1_cpld",
        "sw_device": "ttl_urukul1_sw2"
    }
}

device_db["urukul1_ch3"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 7,
        "cpld_device": "urukul1_cpld",
        "sw_device": "ttl_urukul1_sw3"
    }
}

device_db["eeprom_urukul2"] = {
    "type": "local",
    "module": "artiq.coredevice.kasli_i2c",
    "class": "KasliEEPROM",
    "arguments": {"port": "EEM10"}
}

device_db["spi_urukul2"] = {
    "type": "local",
    "module": "artiq.coredevice.spi2",
    "class": "SPIMaster",
    "arguments": {"channel": 0x000029}
}

device_db["ttl_urukul2_io_update"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00002a}
}

device_db["ttl_urukul2_sw0"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00002b}
}

device_db["ttl_urukul2_sw1"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00002c}
}

device_db["ttl_urukul2_sw2"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00002d}
}

device_db["ttl_urukul2_sw3"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x00002e}
}

device_db["urukul2_cpld"] = {
    "type": "local",
    "module": "artiq.coredevice.urukul",
    "class": "CPLD",
    "arguments": {
        "spi_device": "spi_urukul2",
        "sync_device": None,
        "io_update_device": "ttl_urukul2_io_update",
        "refclk": 125000000.0,
        "clk_sel": 2
    }
}

device_db["urukul2_ch0"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 4,
        "cpld_device": "urukul2_cpld",
        "sw_device": "ttl_urukul2_sw0"
    }
}

device_db["urukul2_ch1"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 5,
        "cpld_device": "urukul2_cpld",
        "sw_device": "ttl_urukul2_sw1"
    }
}

device_db["urukul2_ch2"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 6,
        "cpld_device": "urukul2_cpld",
        "sw_device": "ttl_urukul2_sw2"
    }
}

device_db["urukul2_ch3"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 7,
        "cpld_device": "urukul2_cpld",
        "sw_device": "ttl_urukul2_sw3"
    }
}
# DEST#1 peripherals

device_db["ttl24"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010000},
}

device_db["ttl25"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010001},
}

device_db["ttl26"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010002},
}

device_db["ttl27"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010003},
}

device_db["ttl28"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010004},
}

device_db["ttl29"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010005},
}

device_db["ttl30"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010006},
}

device_db["ttl31"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010007},
}

device_db["ttl32"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010008},
}

device_db["ttl33"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010009},
}

device_db["ttl34"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01000a},
}

device_db["ttl35"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01000b},
}

device_db["ttl36"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01000c},
}

device_db["ttl37"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01000d},
}

device_db["ttl38"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01000e},
}

device_db["ttl39"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01000f},
}

device_db["eeprom_urukul3"] = {
    "type": "local",
    "module": "artiq.coredevice.kasli_i2c",
    "class": "KasliEEPROM",
    "arguments": {"port": "EEM2"}
}

device_db["spi_urukul3"] = {
    "type": "local",
    "module": "artiq.coredevice.spi2",
    "class": "SPIMaster",
    "arguments": {"channel": 0x010010}
}

device_db["ttl_urukul3_io_update"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010011}
}

device_db["ttl_urukul3_sw0"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010012}
}

device_db["ttl_urukul3_sw1"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010013}
}

device_db["ttl_urukul3_sw2"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010014}
}

device_db["ttl_urukul3_sw3"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010015}
}

device_db["urukul3_cpld"] = {
    "type": "local",
    "module": "artiq.coredevice.urukul",
    "class": "CPLD",
    "arguments": {
        "spi_device": "spi_urukul3",
        "sync_device": None,
        "io_update_device": "ttl_urukul3_io_update",
        "refclk": 125000000.0,
        "clk_sel": 2
    }
}

device_db["urukul3_ch0"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 4,
        "cpld_device": "urukul3_cpld",
        "sw_device": "ttl_urukul3_sw0"
    }
}

device_db["urukul3_ch1"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 5,
        "cpld_device": "urukul3_cpld",
        "sw_device": "ttl_urukul3_sw1"
    }
}

device_db["urukul3_ch2"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 6,
        "cpld_device": "urukul3_cpld",
        "sw_device": "ttl_urukul3_sw2"
    }
}

device_db["urukul3_ch3"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 7,
        "cpld_device": "urukul3_cpld",
        "sw_device": "ttl_urukul3_sw3"
    }
}

device_db["eeprom_urukul4"] = {
    "type": "local",
    "module": "artiq.coredevice.kasli_i2c",
    "class": "KasliEEPROM",
    "arguments": {"port": "EEM4"}
}

device_db["spi_urukul4"] = {
    "type": "local",
    "module": "artiq.coredevice.spi2",
    "class": "SPIMaster",
    "arguments": {"channel": 0x010016}
}

device_db["ttl_urukul4_io_update"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010017}
}

device_db["ttl_urukul4_sw0"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010018}
}

device_db["ttl_urukul4_sw1"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010019}
}

device_db["ttl_urukul4_sw2"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01001a}
}

device_db["ttl_urukul4_sw3"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01001b}
}

device_db["urukul4_cpld"] = {
    "type": "local",
    "module": "artiq.coredevice.urukul",
    "class": "CPLD",
    "arguments": {
        "spi_device": "spi_urukul4",
        "sync_device": None,
        "io_update_device": "ttl_urukul4_io_update",
        "refclk": 125000000.0,
        "clk_sel": 2
    }
}

device_db["urukul4_ch0"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 4,
        "cpld_device": "urukul4_cpld",
        "sw_device": "ttl_urukul4_sw0"
    }
}

device_db["urukul4_ch1"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 5,
        "cpld_device": "urukul4_cpld",
        "sw_device": "ttl_urukul4_sw1"
    }
}

device_db["urukul4_ch2"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 6,
        "cpld_device": "urukul4_cpld",
        "sw_device": "ttl_urukul4_sw2"
    }
}

device_db["urukul4_ch3"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 7,
        "cpld_device": "urukul4_cpld",
        "sw_device": "ttl_urukul4_sw3"
    }
}

device_db["eeprom_urukul5"] = {
    "type": "local",
    "module": "artiq.coredevice.kasli_i2c",
    "class": "KasliEEPROM",
    "arguments": {"port": "EEM6"}
}

device_db["spi_urukul5"] = {
    "type": "local",
    "module": "artiq.coredevice.spi2",
    "class": "SPIMaster",
    "arguments": {"channel": 0x01001c}
}

device_db["ttl_urukul5_io_update"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01001d}
}

device_db["ttl_urukul5_sw0"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01001e}
}

device_db["ttl_urukul5_sw1"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x01001f}
}

device_db["ttl_urukul5_sw2"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010020}
}

device_db["ttl_urukul5_sw3"] = {
    "type": "local",
    "module": "artiq.coredevice.ttl",
    "class": "TTLOut",
    "arguments": {"channel": 0x010021}
}

device_db["urukul5_cpld"] = {
    "type": "local",
    "module": "artiq.coredevice.urukul",
    "class": "CPLD",
    "arguments": {
        "spi_device": "spi_urukul5",
        "sync_device": None,
        "io_update_device": "ttl_urukul5_io_update",
        "refclk": 125000000.0,
        "clk_sel": 2
    }
}

device_db["urukul5_ch0"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 4,
        "cpld_device": "urukul5_cpld",
        "sw_device": "ttl_urukul5_sw0"
    }
}

device_db["urukul5_ch1"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 5,
        "cpld_device": "urukul5_cpld",
        "sw_device": "ttl_urukul5_sw1"
    }
}

device_db["urukul5_ch2"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 6,
        "cpld_device": "urukul5_cpld",
        "sw_device": "ttl_urukul5_sw2"
    }
}

device_db["urukul5_ch3"] = {
    "type": "local",
    "module": "artiq.coredevice.ad9910",
    "class": "AD9910",
    "arguments": {
        "pll_n": 32,
        "chip_select": 7,
        "cpld_device": "urukul5_cpld",
        "sw_device": "ttl_urukul5_sw3"
    }
}