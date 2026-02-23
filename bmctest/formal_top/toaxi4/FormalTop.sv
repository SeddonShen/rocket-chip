module FormalTop;
(* gclk *) wire glb_clk;
wire clock;
wire reset;
wire io_finished;
wire io_start;

reg reg_reset = 1'b1;
always @(posedge glb_clk) begin
  if (reg_reset) reg_reset <= 1'b0;
end

assign clock = glb_clk;
assign reset = reg_reset;

StandaloneToAXI4 dut(
  .clock,
  .reset,
  .io_finished,
  .io_start
);
endmodule
