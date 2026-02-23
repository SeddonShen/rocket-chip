module SimTop(input clock, input reset, output io_success);
  import "DPI-C" function byte unsigned fuzz_get_byte();

  wire [71:0] io_encoded;
  wire [63:0] io_decoded;
  wire io_correctable;
  wire io_uncorrectable;

  reg [7:0] fuzz_b0;
  reg [63:0] fuzz_dataIn;

  always @(posedge clock) begin
    if (reset) begin
      fuzz_b0 <= 8'b0;
      fuzz_dataIn <= 64'b0;
    end else begin
      fuzz_b0 <= {fuzz_get_byte()};
      fuzz_dataIn <= {fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(),
                      fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte(), fuzz_get_byte()};
    end
  end

  ECCModule dut(
    .clock(clock), .reset(reset),
    .io_dataIn(fuzz_dataIn),
    .io_poison(fuzz_b0[0]),
    .io_encoded(io_encoded),
    .io_decoded(io_decoded),
    .io_correctable(io_correctable),
    .io_uncorrectable(io_uncorrectable)
  );
  assign io_success = 1'b0;
endmodule
