module SimTop(input clock, input reset, output io_success);
  import "DPI-C" function byte unsigned fuzz_get_byte();

  wire [3:0] io_currState;
  reg [7:0] fuzz_b0;

  always @(posedge clock) begin
    if (reset) fuzz_b0 <= 8'b0;
    else       fuzz_b0 <= {fuzz_get_byte()};
  end

  JtagStateMachine dut(
    .clock(clock), .reset(reset),
    .io_tms(fuzz_b0[0]),
    .io_currState(io_currState)
  );
  assign io_success = 1'b0;
endmodule
