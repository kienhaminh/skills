import assert from "node:assert/strict";
import test from "node:test";
import { canUpload } from "../src/quota.mjs";

test("allows an upload at the exact quota", () => assert.equal(canUpload(7, 10, 3), true));
test("rejects an upload above quota", () => assert.equal(canUpload(8, 10, 3), false));
