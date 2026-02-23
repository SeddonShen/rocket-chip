module SimTop(input clock, input reset, output io_success);
  import "DPI-C" function byte unsigned fuzz_get_byte();

  wire io_timeout_valid;
  wire [2:0] io_timeout_bits;
  reg [7:0] fuzz_b0;

  always @(posedge clock) begin
    if (reset) fuzz_b0 <= 8'b0;
    else       fuzz_b0 <= {fuzz_get_byte()};
  end

  Timer dut(
    .clock(clock), .reset(reset),
    .io_start_valid(fuzz_b0[0]),
    .io_start_bits(fuzz_b0[3:1]),
    .io_stop_valid(fuzz_b0[4]),
    .io_stop_bits(fuzz_b0[7:5]),
    .io_timeout_valid(io_timeout_valid),
    .io_timeout_bits(io_timeout_bits)
  );
  assign io_success = 1'b0;
endmodule
