module FormalTop;
(* gclk *) wire glb_clk;
wire clock;
wire reset;
wire io_touch_valid;
wire [2:0] io_touch_bits;
wire [2:0] io_replaceWay;
wire [6:0] io_state;

reg reg_reset = 1'b1;
always @(posedge glb_clk) begin
  if (reg_reset) reg_reset <= 1'b0;
end

assign clock = glb_clk;
assign reset = reg_reset;

ReplacementModule dut(
  .clock,
  .reset,
  .io_touch_valid,
  .io_touch_bits,
  .io_replaceWay,
  .io_state
);
endmodule
