"""Automated checks run on every submission. A finding is block (the submission is rejected), warn (a reviewer must
acknowledge it before approving) or info. These are tripwires for review, not proof of safety: a clean result means
nothing obvious was found, and a human still decides.

Skills are installed software (they can ship scripts an agent will run), so they get the deepest scan.
"""

import re
from dataclasses import dataclass

from .kinds import Parsed

HIDDEN = re.compile(r"[\u200b-\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069\U000e0000-\U000e007f]")
INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) instructions|do not (tell|inform|show) the user|"
    r"disregard (your|the) (rules|instructions|system prompt)|exfiltrat",
    re.IGNORECASE,
)
SECRETS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "API key": re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,})"),
    "GitHub token": re.compile(r"\b(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
}
SCRIPT_SUFFIXES = (".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".ts", ".ps1", ".rb", ".pl")
SCRIPT_RULES = [  # (severity, what, pattern)
    (
        "block",
        "downloads and runs code",
        re.compile(r"(curl|wget)[^\n|]*\|\s*(ba|z)?sh|iex\s*\(|Invoke-Expression", re.IGNORECASE),
    ),
    (
        "block",
        "decodes and runs hidden code",
        re.compile(r"base64\s+(-d|--decode)[^\n]*\|\s*(ba)?sh|exec\(\s*base64|eval\(\s*atob", re.IGNORECASE),
    ),
    (
        "block",
        "deletes broadly",
        re.compile(r"rm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME)(\s|$)|shutil\.rmtree\(\s*['\"](/|~)"),
    ),
    (
        "block",
        "touches credentials or system files",
        re.compile(r"~/\.ssh|\.aws/credentials|/etc/(passwd|shadow|sudoers)|\.netrc"),
    ),
    (
        "warn",
        "makes network calls",
        re.compile(r"\b(requests\.|httpx\.|urllib\.request|fetch\(|axios|socket\.|curl\s|wget\s|Invoke-WebRequest)"),
    ),
    (
        "warn",
        "runs shell commands or dynamic code",
        re.compile(r"\b(subprocess\.|os\.system|os\.popen|child_process|eval\(|exec\()"),
    ),
    ("warn", "changes permissions", re.compile(r"chmod\s+(777|\+s)|setuid", re.IGNORECASE)),
]
BINARY_MAGIC = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa\xcf")
REGISTRY_TYPES = {"npm", "pypi", "oci", "nuget", "mcpb"}


@dataclass
class Finding:
    check: str
    severity: str  # block | warn | info
    message: str
    location: str = ""


def _text_checks(text: str, where: str, out: list[Finding]) -> None:
    if HIDDEN.search(text):
        out.append(
            Finding(
                "hidden_unicode", "block", "invisible or bidirectional control characters can hide instructions", where
            )
        )
    if INJECTION.search(text):
        out.append(Finding("injection_phrase", "warn", "text reads like an instruction to override the agent", where))
    for label, pattern in SECRETS.items():
        if pattern.search(text):
            out.append(Finding("secret", "block", f"looks like a committed {label}", where))


def _url_checks(url: str, where: str, out: list[Finding]) -> None:
    if not url.startswith("https://"):
        out.append(Finding("https_only", "block", "endpoints must use HTTPS", where))


def run(p: Parsed, licenses_allowed: list[str], require_auth_on_agents: bool) -> list[Finding]:
    out: list[Finding] = []
    _text_checks(f"{p.title}\n{p.description}", "description", out)

    if p.kind == "mcp_server":
        for i, remote in enumerate(p.document.get("remotes") or []):
            _url_checks(str(remote.get("url", "")), f"remotes[{i}]", out)
        for i, pkg in enumerate(p.document.get("packages") or []):
            where = f"packages[{i}]"
            if pkg.get("registryType") not in REGISTRY_TYPES:
                out.append(
                    Finding("package_source", "warn", f"unknown registry type {pkg.get('registryType')!r}", where)
                )
            if pkg.get("registryType") == "mcpb" and not pkg.get("fileSha256"):
                out.append(Finding("integrity", "block", "MCPB packages need fileSha256", where))
            if pkg.get("registryType") == "oci" and "@sha256:" not in str(pkg.get("identifier", "")):
                out.append(Finding("integrity", "warn", "pin the container image by digest (@sha256:...)", where))
            if pkg.get("registryType") in ("npm", "pypi", "nuget") and not pkg.get("version"):
                out.append(Finding("integrity", "warn", "pin the package version", where))
        if not p.document.get("repository"):
            out.append(Finding("provenance", "info", "no source repository listed", "repository"))

    if p.kind == "a2a_agent":
        for i, iface in enumerate(p.document.get("supportedInterfaces") or []):
            _url_checks(str(iface.get("url", "")), f"supportedInterfaces[{i}]", out)
        if require_auth_on_agents and not p.document.get("securitySchemes"):
            out.append(Finding("authentication", "block", "the agent declares no securitySchemes", "securitySchemes"))
        if not p.document.get("signatures"):
            out.append(Finding("provenance", "info", "the agent card is not signed", "signatures"))
        for i, skill in enumerate(p.document.get("skills") or []):
            _text_checks(f"{skill.get('name', '')}\n{skill.get('description', '')}", f"skills[{i}]", out)

    if p.kind == "skill":
        if not p.license:
            out.append(Finding("license", "warn", "no license declared", "SKILL.md"))
        elif not any(
            p.license == a or p.license.startswith(a + " ") or p.license.startswith(a + ".") for a in licenses_allowed
        ):
            out.append(Finding("license", "warn", f"license {p.license!r} is not on the allow-list", "SKILL.md"))
        if p.document.get("_body_lines", 0) > 500:
            out.append(Finding("size", "info", "SKILL.md is over 500 lines; move detail into references/", "SKILL.md"))
        tools = str(p.document.get("allowed-tools", ""))
        if re.search(r"Bash(\(\*\)|\b(?!\())", tools):
            out.append(Finding("tool_scope", "warn", "pre-approves unrestricted shell access", "allowed-tools"))
        for path, data in sorted(p.files.items()):
            if data.startswith(BINARY_MAGIC):
                out.append(Finding("binary", "block", "contains a compiled executable", path))
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue  # images and other assets
            _text_checks(text, path, out)
            if path.endswith(SCRIPT_SUFFIXES) or "/scripts/" in path:
                for severity, what, pattern in SCRIPT_RULES:
                    m = pattern.search(text)
                    if m:
                        line = text.count("\n", 0, m.start()) + 1
                        out.append(Finding("script", severity, f"script {what}", f"{path}:{line}"))
    return out
