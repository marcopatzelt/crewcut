# Research and coding projects

All crew members can research public sources, write code and run local experiments with Claude Code or Codex.
They use the engine's existing terminal and file tools, plus public HTTP requests or its available search tools.
This does not add a paid search service or expose the user's desktop.

Use `crewcut workspace create render-study` to make a persistent project. Add `--episode 015-example` to record
its episode. `crewcut workspace list` lists existing projects. Repeating create keeps existing files intact.

Projects live in `workspaces/<name>/` inside the user's studio folder, mounted at `/studio/workspaces` in Docker.
They survive app updates and remain private. `CREWCUT_WORKSPACES` tells each agent where this root is.
The folders are `code/`, `research/`, `results/` and `logs/`. Dependencies belong in a project-local virtual
environment or `node_modules`, not in Crewcut's installed packages. Public repositories may be cloned here.

Channel research can use a workspace without creating a fake episode. Episode deliverables still go in the episode.
Copy a final report into `brief/` before requesting approval. Record sources, commands, assumptions and results.
Keep estimates visibly separate from measurements. Container hardware access is not proof of laptop GPU access.

## Boundaries

The host source repository is not mounted by the standard Compose setup. No new host folders, Docker socket,
desktop controls, credentials or device access are granted. Existing spending and publishing cards still apply.
Agents must not change Crewcut's code, engine settings or security rules. They must not run destructive cleanup
without approval. Heavy experiments use the existing render commands and shared heavy-job lane.

The workspace path checks prevent traversal and symbolic-link destinations in this command. The agent instructions
are not an operating-system sandbox: the existing engine can still execute terminal commands inside its container.
Do not treat downloaded code as safe merely because it lives in a workspace. Review it before execution.

New jobs receive the instructions. Restart the service only when no agent or tool job is running, so existing work
is not interrupted. Claude's generated crew plugin also contains these rules for delegated crew members.
