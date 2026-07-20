import assert from "node:assert/strict";
import test from "node:test";
import { reportRows } from "./report.mjs";

test("projects report rows", () => {
  assert.deepEqual(reportRows([{ id: "a", amount: 2, secret: "x" }]), [{ id: "a", amount: 2 }]);
});
