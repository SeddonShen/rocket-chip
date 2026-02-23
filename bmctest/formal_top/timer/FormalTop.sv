module FormalTop;
(* gclk *) wire glb_clk;
wire clock;
wire reset;
wire io_start_valid;
wire [2:0] io_start_bits;
wire io_stop_valid;
wire [2:0] io_stop_bits;
wire io_timeout_valid;
wire [2:0] io_timeout_bits;

reg reg_reset = 1'b1;
always @(posedge glb_clk) begin
  if (reg_reset) reg_reset <= 1'b0;
end

assign clock = glb_clk;
assign reset = reg_reset;

Timer dut(
  .clock,
  .reset,
  .io_start_valid,
  .io_start_bits,
  .io_stop_valid,
  .io_stop_bits,
  .io_timeout_valid,
  .io_timeout_bits
);
endmodule
