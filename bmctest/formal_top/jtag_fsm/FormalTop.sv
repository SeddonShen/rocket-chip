module FormalTop;
(* gclk *) wire glb_clk;
wire clock;
wire reset;
wire io_tms;
wire [3:0] io_currState;

reg reg_reset = 1'b1;
always @(posedge glb_clk) begin
  if (reg_reset) reg_reset <= 1'b0;
end

assign clock = glb_clk;
assign reset = reg_reset;

JtagStateMachine dut(
  .clock,
  .reset,
  .io_tms,
  .io_currState
);
endmodule
