module SimTop(input clock, input reset, output io_success);
  reg start_reg;
  always @(posedge clock) begin
    if (reset) start_reg <= 1'b0;
    else       start_reg <= 1'b1;
  end
  StandaloneXbar dut(
    .clock(clock), .reset(reset),
    .io_finished(io_success), .io_start(start_reg)
  );
endmodule
