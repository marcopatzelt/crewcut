import test from "node:test";
import assert from "node:assert/strict";
import { parsePrompterRequest, prompterUrl } from "../prompter-protocol";

test("prompter requests accept only episode identifiers and matching filenames", () => {
  const request = { id: "a".repeat(32), episode: "015-example", created: Date.now() / 1000, status: "pending" };
  assert.deepEqual(parsePrompterRequest(request, `${request.id}.json`), request);
  for (const episode of ["../file", "http://example.org", "/tmp/file", "x; touch /tmp/file"]) {
    assert.equal(parsePrompterRequest({ ...request, episode }, `${request.id}.json`), null);
  }
  assert.equal(parsePrompterRequest(request, "other.json"), null);
  assert.equal(parsePrompterRequest({ ...request, status: "opened" }, `${request.id}.json`), null);
  assert.equal(parsePrompterRequest({ ...request, created: Infinity }, `${request.id}.json`), null);
});

test("the window URL always uses the fixed local prompter server", () => {
  assert.equal(prompterUrl("valid_token-12", 4748), "http://127.0.0.1:4748/p/valid_token-12");
  for (const token of ["../escape", "https://example.org", "token?next=x", "<script>", null]) {
    assert.throws(() => prompterUrl(token, 4748));
  }
});
