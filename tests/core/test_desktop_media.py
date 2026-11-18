import json

import pytest

from crewcut import desktop_media, paths
from crewcut.conductor import prompts


def test_request_is_durable_and_status_requires_safe_id(studio):
    paths.state_dir().mkdir(exist_ok=True)
    result = desktop_media.request("list", source="test", path="DCIM", offset=0)
    assert desktop_media.status(result["id"]) == result
    target = paths.state_dir() / "desktop-media" / f"{result['id']}.json"
    target.write_text(json.dumps({**result, "created": 0}))
    assert desktop_media.status(result["id"])["status"] == "failed"
    with pytest.raises(ValueError):
        desktop_media.status("../private")
    with pytest.raises(ValueError):
        desktop_media.request("shell", command="anything")


def test_agent_knows_to_discover_sources_before_claiming_no_access():
    assert "crewcut media sources" in prompts.WORKSPACE_RULES
