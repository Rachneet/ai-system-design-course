"""Parse and validate the three kinds of artifact against their published specs.

mcp_server  server.json, validated with the official MCP registry schema (vendored in schemas/)
a2a_agent   an A2A Agent Card (spec 1.0): required fields per section 4.4 of the specification
skill       an Agent Skills package: a zip holding <name>/SKILL.md with YAML frontmatter (agentskills.io)

Validation failures raise Invalid with every problem found, so a publisher fixes them in one round.
"""

import hashlib
import io
import json
import re
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml
from jsonschema import Draft7Validator

KINDS = ("mcp_server", "a2a_agent", "skill")
_SCHEMA = json.loads((Path(__file__).parent / "schemas" / "server.schema.json").read_text())
_SERVER = Draft7Validator(_SCHEMA)
VERSION_RANGE = re.compile(r"^[\^~<>=]|(^|\.)[xX*](\.|$)|\s|\|\|")  # ranges like ^1.2, 1.x, >=2, 1.0 - 2.0
SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
AGENT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class Invalid(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Parsed:
    kind: str
    name: str
    version: str
    title: str
    description: str
    document: dict  # what discovery returns: server.json, the agent card, or the skill's frontmatter
    digest: str
    license: str | None = None
    tags: list[str] = field(default_factory=list)
    blob: bytes | None = None  # skill packages only
    files: dict[str, bytes] = field(default_factory=dict)  # skill packages only, for static checks
    tools: list[dict] | None = None  # MCP servers only: the reviewed tools/list result, pinned by tools_digest
    tools_digest: str | None = None


def canonical_digest(doc) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


TOOL_FIELDS = ("name", "title", "description", "inputSchema", "outputSchema", "annotations")


def tools_digest(tools: list[dict]) -> str:
    """The pin for a server's tool list: what a model reads and what it may send, sorted by name, canonical JSON.
    Gateways compute the same digest over the live tools/list result (Checkpoint's catalog.tools_digest)."""
    return canonical_digest(sorted(({k: t[k] for k in TOOL_FIELDS if k in t} for t in tools), key=lambda t: t["name"]))


def check_tools(tools: list, problems: list[str]) -> None:
    names = set()
    if len(tools) > 500:
        problems.append("tools: at most 500 tools")
    for i, t in enumerate(tools):
        if not isinstance(t, dict) or not isinstance(t.get("name"), str) or not t["name"]:
            problems.append(f"tools[{i}] needs a name")
            continue
        if not isinstance(t.get("inputSchema"), dict):
            problems.append(f"tools[{i}] ({t['name']}) needs an inputSchema object")
        if t["name"] in names:
            problems.append(f"tools[{i}] repeats the name {t['name']!r}")
        names.add(t["name"])


def check_version(version: str, problems: list[str]) -> None:
    if (
        not version
        or len(version) > 255
        or VERSION_RANGE.search(version)
        or version.lower() in ("latest", "stable", "main")
    ):
        problems.append(f"version {version!r} must be one exact version, not a range or wildcard")


def parse_mcp_server(doc: dict, tools: list | None = None) -> Parsed:
    problems = [
        f"{'/'.join(map(str, e.absolute_path)) or 'server.json'}: {e.message}"
        for e in sorted(_SERVER.iter_errors(doc), key=lambda e: list(e.absolute_path))
    ]
    check_version(str(doc.get("version", "")), problems)
    if tools is not None:
        check_tools(tools, problems)
    if problems:
        raise Invalid(problems)
    return Parsed(
        kind="mcp_server",
        name=doc["name"],
        version=doc["version"],
        title=doc.get("title") or doc["name"],
        description=doc["description"],
        document=doc,
        digest=canonical_digest(doc),
        tools=[{k: t[k] for k in TOOL_FIELDS if k in t} for t in tools] if tools is not None else None,
        tools_digest=tools_digest(tools) if tools is not None else None,
    )


def parse_a2a_agent(agent_id: str, card: dict) -> Parsed:
    problems = []
    if not AGENT_ID.match(agent_id or ""):
        problems.append("id must be 2 to 63 lowercase letters, digits or hyphens")
    for key, kind in (
        ("name", str),
        ("description", str),
        ("version", str),
        ("supportedInterfaces", list),
        ("capabilities", dict),
        ("defaultInputModes", list),
        ("defaultOutputModes", list),
        ("skills", list),
    ):
        if not isinstance(card.get(key), kind) or (kind in (str, list) and not card.get(key)):
            problems.append(f"agent card needs a non-empty {key} ({kind.__name__})")
    for i, iface in enumerate(card.get("supportedInterfaces") or []):
        for key in ("url", "protocolBinding", "protocolVersion"):
            if not isinstance(iface, dict) or not iface.get(key):
                problems.append(f"supportedInterfaces[{i}] needs {key}")
    seen = set()
    for i, skill in enumerate(card.get("skills") or []):
        if not isinstance(skill, dict):
            problems.append(f"skills[{i}] must be an object")
            continue
        for key in ("id", "name", "description"):
            if not skill.get(key):
                problems.append(f"skills[{i}] needs {key}")
        if not isinstance(skill.get("tags"), list):
            problems.append(f"skills[{i}] needs tags (a list)")
        if skill.get("id") in seen:
            problems.append(f"skills[{i}] repeats id {skill.get('id')!r}")
        seen.add(skill.get("id"))
    check_version(str(card.get("version", "")), problems)
    if problems:
        raise Invalid(problems)
    tags = sorted({t for s in card["skills"] for t in s.get("tags", []) if isinstance(t, str)})
    return Parsed(
        kind="a2a_agent",
        name=agent_id,
        version=card["version"],
        title=card["name"],
        description=card["description"],
        document=card,
        digest=canonical_digest(card),
        tags=tags,
    )


def _frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise Invalid(["SKILL.md must start with YAML frontmatter between --- lines"])
    parts = text.split("\n---", 1)
    if len(parts) != 2:
        raise Invalid(["SKILL.md frontmatter is not closed with ---"])
    try:
        meta = yaml.safe_load(parts[0][3:]) or {}
    except yaml.YAMLError as e:
        raise Invalid([f"SKILL.md frontmatter is not valid YAML: {e}"]) from None
    if not isinstance(meta, dict):
        raise Invalid(["SKILL.md frontmatter must be a mapping"])
    return meta, parts[1].split("\n", 1)[1] if "\n" in parts[1] else ""


def safe_unzip(blob: bytes, max_bytes: int, max_files: int) -> dict[str, bytes]:
    """Reject archives that could escape the extraction directory or exhaust memory, before reading any file."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise Invalid(["the skill package must be a zip file"]) from None
    infos = [i for i in zf.infolist() if not i.is_dir()]
    problems, total = [], 0
    if len(infos) > max_files:
        problems.append(f"package has {len(infos)} files; the limit is {max_files}")
    for info in infos:
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
            problems.append(f"{info.filename}: paths must be relative and stay inside the package")
        if stat.S_ISLNK(info.external_attr >> 16):
            problems.append(f"{info.filename}: symbolic links are not allowed")
        total += info.file_size
        if info.compress_size and info.file_size / info.compress_size > 200 and info.file_size > 1_000_000:
            problems.append(f"{info.filename}: compression ratio suggests a zip bomb")
    if total > max_bytes:
        problems.append(f"package unpacks to {total} bytes; the limit is {max_bytes}")
    if problems:
        raise Invalid(problems)
    return {i.filename: zf.read(i) for i in infos}


def parse_skill(blob: bytes, version: str, max_bytes: int, max_files: int) -> Parsed:
    files = safe_unzip(blob, max_bytes, max_files)
    roots = {PurePosixPath(p).parts[0] for p in files}
    if len(roots) != 1 or f"{next(iter(roots))}/SKILL.md" not in files:
        raise Invalid(["the zip must contain one top-level directory holding SKILL.md (<name>/SKILL.md)"])
    root = next(iter(roots))
    try:
        text = files[f"{root}/SKILL.md"].decode("utf-8")
    except UnicodeDecodeError:
        raise Invalid(["SKILL.md must be UTF-8 text"]) from None
    meta, body = _frontmatter(text)
    problems = []
    name, description = meta.get("name"), meta.get("description")
    if not isinstance(name, str) or not (1 <= len(name) <= 64) or not SKILL_NAME.match(name):
        problems.append(
            "name must be 1 to 64 lowercase letters, digits and single hyphens, not starting or ending with one"
        )
    elif name != root:
        problems.append(f"name {name!r} must match the directory name {root!r}")
    if not isinstance(description, str) or not (1 <= len(description) <= 1024):
        problems.append("description must be 1 to 1024 characters")
    compat = meta.get("compatibility")
    if compat is not None and (not isinstance(compat, str) or not (1 <= len(compat) <= 500)):
        problems.append("compatibility must be 1 to 500 characters")
    md = meta.get("metadata")
    if md is not None and (
        not isinstance(md, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in md.items())
    ):
        problems.append("metadata must map strings to strings")
    check_version(version, problems)
    if problems:
        raise Invalid(problems)
    lic = meta.get("license")
    return Parsed(
        kind="skill",
        name=name,
        version=version,
        title=name,
        description=description,
        document=meta | {"_body_lines": body.count("\n") + 1},
        digest=hashlib.sha256(blob).hexdigest(),
        license=lic if isinstance(lic, str) else None,
        blob=blob,
        files=files,
    )
