module FormalTop;
(* gclk *) wire glb_clk;
wire clock;
wire reset;
wire io_enq_ready;
wire io_enq_valid;
wire [63:0] io_enq_bits_data;
wire [3:0] io_enq_bits_tag;
wire io_deq_valid;
wire [3:0] io_deq_tag;
wire [63:0] io_deq_data;
wire io_deq_matches;

reg reg_reset = 1'b1;
always @(posedge glb_clk) begin
  if (reg_reset) reg_reset <= 1'b0;
end

assign clock = glb_clk;
assign reset = reg_reset;

ReorderQueue dut(
  .clock,
  .reset,
  .io_enq_ready,
  .io_enq_valid,
  .io_enq_bits_data,
  .io_enq_bits_tag,
  .io_deq_valid,
  .io_deq_tag,
  .io_deq_data,
  .io_deq_matches
);
endmodule
