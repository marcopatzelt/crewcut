import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile, rm, symlink } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { DesktopMedia } from "../media";

test("media sources refresh after hotplug, browse and copy without changing the source", async () => {
  const root = await mkdtemp(join(tmpdir(), "crewcut-media-"));
  try {
    const studio = join(root, "studio"), card = join(root, "card");
    await mkdir(join(studio, "episodes", "001-test"), { recursive: true });
    await writeFile(join(studio, "episodes", "001-test", "project.json"), "{}");
    const service = new DesktopMedia(() => studio, async () => [{ path: card, label: "Card" }]);
    assert.deepEqual(await service.sources(), []);
    await mkdir(join(card, "DCIM"), { recursive: true });
    await writeFile(join(card, "DCIM", "take.MP4"), "synthetic recording");
    await writeFile(join(card, "private.txt"), "not media");
    const source = (await service.sources())[0].id;
    const listing = await service.execute({ action: "list", source, path: "" });
    assert.equal(listing.entries?.length, 1);
    const result = await service.execute({ action: "import", source, path: "DCIM/take.MP4", episode: "001-test" });
    assert.equal(await readFile(join(studio, result.file!.replace("/studio/", "")), "utf8"), "synthetic recording");
    assert.equal(await readFile(join(card, "DCIM", "take.MP4"), "utf8"), "synthetic recording");
    await assert.rejects(service.execute({ action: "import", source, path: "private.txt", episode: "001-test" }));
    await assert.rejects(service.execute({ action: "list", source, path: "../studio" }));
    await symlink(studio, join(card, "escape"));
    await assert.rejects(service.execute({ action: "list", source, path: "escape" }));
    await rm(join(studio, "inbox"), { recursive: true });
    await symlink(card, join(studio, "inbox"));
    await assert.rejects(service.execute({ action: "import", source, path: "DCIM/take.MP4", episode: "001-test" }));
    await rm(card, { recursive: true });
    assert.deepEqual(await service.sources(), []);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("media queue handles a request without opening arbitrary host files", async () => {
  const root = await mkdtemp(join(tmpdir(), "crewcut-media-"));
  try {
    const queue = join(root, ".crewcut", "desktop-media");
    await mkdir(queue, { recursive: true });
    const id = "a".repeat(32), file = join(queue, `${id}.json`);
    await writeFile(file, JSON.stringify({ id, action: "sources", created: Date.now() / 1000, status: "pending" }));
    const service = new DesktopMedia(() => root, async () => []);
    await service.poll();
    const result = JSON.parse(await readFile(file, "utf8"));
    assert.equal(result.status, "done");
    assert.deepEqual(result.sources, []);
  } finally { await rm(root, { recursive: true, force: true }); }
});
