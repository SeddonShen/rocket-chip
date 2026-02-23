module FormalTop;
(* gclk *) wire glb_clk;
wire clock;
wire reset;
wire io_free_valid;
wire [4:0] io_free_bits;
wire io_alloc_ready;
wire io_alloc_valid;
wire [4:0] io_alloc_bits;

reg reg_reset = 1'b1;
always @(posedge glb_clk) begin
  if (reg_reset) reg_reset <= 1'b0;
end

assign clock = glb_clk;
assign reset = reg_reset;

IDPool dut(
  .clock,
  .reset,
  .io_free_valid,
  .io_free_bits,
  .io_alloc_ready,
  .io_alloc_valid,
  .io_alloc_bits
);
endmodule
