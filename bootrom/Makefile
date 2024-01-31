bootrom_img = bootrom.img

CROSS=riscv64-unknown-elf-
GCC=$(CROSS)gcc
OBJCOPY=$(CROSS)objcopy

all: $(bootrom_img)

ifeq ($(CROSS),riscv64-linux-gnu-)
SECTIONS = --only-section=.text*
endif

%.img: %.bin
	dd if=$< of=$@ bs=128 count=1

%.bin: %.elf
	$(OBJCOPY) -O binary $(SECTIONS) $< $@

%.elf: %.S linker.ld
	$(GCC) -Tlinker.ld $< -nostdlib -static -Wl,--no-gc-sections -o $@ -march=rv64g
