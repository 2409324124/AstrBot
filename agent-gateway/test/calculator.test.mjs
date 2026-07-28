import assert from "node:assert/strict";
import test from "node:test";

import { calculateExpression, convertUnits } from "../src/calculator.ts";

test("calculator evaluates bounded scalar arithmetic and common functions", () => {
  assert.equal(calculateExpression("sqrt(81) + 2^3"), 17);
  assert.equal(calculateExpression("round(pi, 4)"), 3.1416);
});

test("calculator rejects assignments and unknown symbols", () => {
  assert.throws(() => calculateExpression("x = 42"), /not allowed/i);
  assert.throws(() => calculateExpression("import(\"fs\")"), /not allowed/i);
});

test("unit converter handles compatible units and rejects incompatible ones", () => {
  assert.deepEqual(convertUnits(5, "kilometer", "meter"), {
    value: 5,
    from: "kilometer",
    to: "meter",
    convertedValue: 5000
  });
  assert.throws(() => convertUnits(1, "meter", "second"), /units do not match/i);
});
