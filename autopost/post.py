"""A post is a folder holding one video file and a post.json describing it.

post.json fields (all optional except one of title/description):
  title          YouTube title (max 100 chars). Defaults to the first line of description.
  description    Main text; used as the caption on every platform unless overridden.
  tags           List of tags (YouTube) / used to build hashtags by adapters that want them.
  made_for_kids  YouTube "made for kids" flag (default false).
  privacy        YouTube privacy: public | unlisted | private (default public).
  platforms      Which platforms to post to (default: all supported).
  captions       Per-platform overrides, e.g. {"linkedin": "...", "instagram": "..."}.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v")
ALL_PLATFORMS = ["youtube", "instagram", "linkedin", "tiktok"]


class PostError(Exception):
    """The post folder or post.json is invalid."""


class Post:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        meta_file = self.folder / "post.json"
        if not meta_file.exists():
            raise PostError(f"{meta_file} not found")
        try:
            self.meta = json.loads(meta_file.read_text())
        except json.JSONDecodeError as e:
            raise PostError(f"{meta_file} is not valid JSON: {e}")
        videos = sorted(p for p in self.folder.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
        if len(videos) != 1:
            raise PostError(f"{self.folder} must contain exactly one video ({', '.join(VIDEO_EXTENSIONS)}), found {len(videos)}")
        self.video: Path = videos[0]
        if not (self.meta.get("description") or self.meta.get("title")):
            raise PostError("post.json needs at least a title or a description")
        unknown = set(self.platforms) - set(ALL_PLATFORMS)
        if unknown:
            raise PostError(f"Unknown platforms in post.json: {', '.join(sorted(unknown))}")

    @property
    def platforms(self) -> List[str]:
        return list(self.meta.get("platforms") or ALL_PLATFORMS)

    @property
    def title(self) -> str:
        title = self.meta.get("title") or self.meta.get("description", "").strip().splitlines()[0]
        return title[:100]

    @property
    def tags(self) -> List[str]:
        return list(self.meta.get("tags") or [])

    @property
    def made_for_kids(self) -> bool:
        return bool(self.meta.get("made_for_kids", False))

    @property
    def privacy(self) -> str:
        return self.meta.get("privacy", "public")

    def caption_for(self, platform: str) -> str:
        override = (self.meta.get("captions") or {}).get(platform)
        return override if override else (self.meta.get("description") or self.meta.get("title", ""))

    # ---- results (result.json) ----
    @property
    def result_file(self) -> Path:
        return self.folder / "result.json"

    def results(self) -> Dict[str, dict]:
        return json.loads(self.result_file.read_text()) if self.result_file.exists() else {}

    def succeeded(self, platform: str) -> bool:
        return self.results().get(platform, {}).get("status") == "ok"

    def record(self, platform: str, status: str, info: Optional[dict] = None, error: Optional[str] = None) -> None:
        data = self.results()
        entry = {"status": status, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if info:
            entry.update(info)
        if error:
            entry["error"] = error
        data[platform] = entry
        self.result_file.write_text(json.dumps(data, indent=2))

    def pending(self) -> List[str]:
        return [p for p in self.platforms if not self.succeeded(p)]
