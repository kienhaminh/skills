import assert from "node:assert/strict";
import test from "node:test";
import { defaultPort } from "../src/config.mjs";

test("default port is 4200", () => assert.equal(defaultPort, 4200));
