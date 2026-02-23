module SimTop(input clock, input reset, output io_success);
  import "DPI-C" function byte unsigned fuzz_get_byte();

  wire io_alloc_valid;
  wire [4:0] io_alloc_bits;
  reg [7:0] fuzz_b0;

  always @(posedge clock) begin
    if (reset) fuzz_b0 <= 8'b0;
    else       fuzz_b0 <= {fuzz_get_byte()};
  end

  IDPool dut(
    .clock(clock), .reset(reset),
    .io_free_valid(fuzz_b0[0]),
    .io_free_bits(fuzz_b0[5:1]),
    .io_alloc_ready(fuzz_b0[6]),
    .io_alloc_valid(io_alloc_valid),
    .io_alloc_bits(io_alloc_bits)
  );
  assign io_success = 1'b0;
endmodule
