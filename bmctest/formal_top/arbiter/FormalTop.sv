module FormalTop;
(* gclk *) wire glb_clk;
wire clock;
wire reset;
wire io_in_0_ready;
wire io_in_0_valid;
wire [63:0] io_in_0_bits;
wire io_in_1_ready;
wire io_in_1_valid;
wire [63:0] io_in_1_bits;
wire io_in_2_ready;
wire io_in_2_valid;
wire [63:0] io_in_2_bits;
wire io_in_3_ready;
wire io_in_3_valid;
wire [63:0] io_in_3_bits;
wire io_out_ready;
wire io_out_valid;
wire [63:0] io_out_bits;

reg reg_reset = 1'b1;
always @(posedge glb_clk) begin
  if (reg_reset) reg_reset <= 1'b0;
end

assign clock = glb_clk;
assign reset = reg_reset;

HellaCountingArbiter dut(
  .clock,
  .reset,
  .io_in_0_ready,
  .io_in_0_valid,
  .io_in_0_bits,
  .io_in_1_ready,
  .io_in_1_valid,
  .io_in_1_bits,
  .io_in_2_ready,
  .io_in_2_valid,
  .io_in_2_bits,
  .io_in_3_ready,
  .io_in_3_valid,
  .io_in_3_bits,
  .io_out_ready,
  .io_out_valid,
  .io_out_bits
);
endmodule
