module SimTop(input clock, input reset, output io_success);
  import "DPI-C" function byte unsigned fuzz_get_byte();

  wire [2:0] io_replaceWay;
  wire [6:0] io_state;
  reg [7:0] fuzz_b0;

  always @(posedge clock) begin
    if (reset) fuzz_b0 <= 8'b0;
    else       fuzz_b0 <= {fuzz_get_byte()};
  end

  ReplacementModule dut(
    .clock(clock), .reset(reset),
    .io_touch_valid(fuzz_b0[0]),
    .io_touch_bits(fuzz_b0[3:1]),
    .io_replaceWay(io_replaceWay),
    .io_state(io_state)
  );
  assign io_success = 1'b0;
endmodule
