module SimTop(input clock, input reset, output io_success);
  import "DPI-C" function byte unsigned fuzz_get_byte();

  wire io_enq_ready;
  wire [63:0] io_deq_data;
  wire io_deq_matches;

  reg [7:0] fuzz_b0, fuzz_b1;
  reg [63:0] fuzz_enq_data;

  always @(posedge clock) begin
    if (reset) begin
      fuzz_b0 <= 8'b0;
      fuzz_b1 <= 8'b0;
      fuzz_enq_data <= 64'b0;
    end else begin
      fuzz_b0 <= {fuzz_get_byte()};
      fuzz_b1 <= {fuzz_get_byte()};
      fuzz_enq_data <= {fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(),
                        fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte()};
    end
  end

  ReorderQueue dut(
    .clock(clock), .reset(reset),
    .io_enq_ready(io_enq_ready),
    .io_enq_valid(fuzz_b0[0]),
    .io_enq_bits_data(fuzz_enq_data),
    .io_enq_bits_tag(fuzz_b1[3:0]),
    .io_deq_valid(fuzz_b0[1]),
    .io_deq_tag(fuzz_b1[7:4]),
    .io_deq_data(io_deq_data),
    .io_deq_matches(io_deq_matches)
  );
  assign io_success = 1'b0;
endmodule
