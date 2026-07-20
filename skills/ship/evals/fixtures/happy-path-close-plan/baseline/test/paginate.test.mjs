import assert from "node:assert/strict";
import test from "node:test";

import { paginate } from "../src/paginate.mjs";

test("returns the first page", () => {
  assert.deepEqual(paginate([1, 2, 3, 4], 2), [1, 2]);
});
