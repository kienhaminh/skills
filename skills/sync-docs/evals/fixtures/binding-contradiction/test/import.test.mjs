import assert from "node:assert/strict";
import test from "node:test";
import { maxBatchSize } from "../src/import.mjs";

test("implementation currently uses twelve", () => assert.equal(maxBatchSize, 12));
