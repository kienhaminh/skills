import assert from "node:assert/strict";
import test from "node:test";

import { isExpired } from "../src/token.mjs";

test("marks past and current tokens expired", () => {
  assert.equal(isExpired(99, 100), true);
  assert.equal(isExpired(100, 100), true);
  assert.equal(isExpired(101, 100), false);
});
