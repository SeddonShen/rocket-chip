module FormalTop;
(* gclk *) wire glb_clk;
wire clock;
wire reset;
wire [63:0] io_dataIn;
wire io_poison;
wire [71:0] io_encoded;
wire [63:0] io_decoded;
wire io_correctable;
wire io_uncorrectable;

reg reg_reset = 1'b1;
always @(posedge glb_clk) begin
  if (reg_reset) reg_reset <= 1'b0;
end

assign clock = glb_clk;
assign reset = reg_reset;

ECCModule dut(
  .clock,
  .reset,
  .io_dataIn,
  .io_poison,
  .io_encoded,
  .io_decoded,
  .io_correctable,
  .io_uncorrectable
);
endmodule
