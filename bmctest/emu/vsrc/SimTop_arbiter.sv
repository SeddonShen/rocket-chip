module SimTop(input clock, input reset, output io_success);
  import "DPI-C" function byte unsigned fuzz_get_byte();

  wire io_in_0_ready;
  wire io_in_1_ready;
  wire io_in_2_ready;
  wire io_in_3_ready;
  wire io_out_valid;
  wire [63:0] io_out_bits;

  reg [7:0] fuzz_b0;
  reg [63:0] fuzz_in0_bits, fuzz_in1_bits, fuzz_in2_bits, fuzz_in3_bits;

  always @(posedge clock) begin
    if (reset) begin
      fuzz_b0 <= 8'b0;
      fuzz_in0_bits <= 64'b0;
      fuzz_in1_bits <= 64'b0;
      fuzz_in2_bits <= 64'b0;
      fuzz_in3_bits <= 64'b0;
    end else begin
      fuzz_b0 <= {fuzz_get_byte()};
      fuzz_in0_bits <= {fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(),
                        fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte()};
      fuzz_in1_bits <= {fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(),
                        fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte()};
      fuzz_in2_bits <= {fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(),
                        fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte()};
      fuzz_in3_bits <= {fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(),
                        fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte()};
    end
  end

  HellaCountingArbiter dut(
    .clock(clock), .reset(reset),
    .io_in_0_ready(io_in_0_ready),
    .io_in_0_valid(fuzz_b0[0]),
    .io_in_0_bits(fuzz_in0_bits),
    .io_in_1_ready(io_in_1_ready),
    .io_in_1_valid(fuzz_b0[1]),
    .io_in_1_bits(fuzz_in1_bits),
    .io_in_2_ready(io_in_2_ready),
    .io_in_2_valid(fuzz_b0[2]),
    .io_in_2_bits(fuzz_in2_bits),
    .io_in_3_ready(io_in_3_ready),
    .io_in_3_valid(fuzz_b0[3]),
    .io_in_3_bits(fuzz_in3_bits),
    .io_out_ready(fuzz_b0[4]),
    .io_out_valid(io_out_valid),
    .io_out_bits(io_out_bits)
  );
  assign io_success = 1'b0;
endmodule
