import json
import re
from pathlib import Path

import yaml
from prometheus_client import REGISTRY

import app.metrics  # noqa: F401 - registers the metrics

OPS = Path(__file__).parent.parent / "ops"


def exported_names() -> set[str]:
    names = set()
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            names.add(sample.name)
        names.add(metric.name)
        names.add(metric.name + "_total")
        names.update({metric.name + s for s in ("_bucket", "_count", "_sum")})
    return names


def referenced(exprs: list[str]) -> set[str]:
    return {m for e in exprs for m in re.findall(r"\b(relay_[a-z_]+)\b", e)}


def test_alerts_and_dashboard_only_use_metrics_that_exist():
    rules = yaml.safe_load((OPS / "prometheus" / "alerts.yml").read_text())
    exprs = [r["expr"] for g in rules["groups"] for r in g["rules"]]
    dash = json.loads((OPS / "grafana" / "relay-dashboard.json").read_text())
    exprs += [t["expr"] for p in dash["panels"] for t in p.get("targets", [])]
    missing = referenced(exprs) - exported_names()
    assert not missing, f"alerts or dashboard reference unknown metrics: {sorted(missing)}"


def test_every_alert_has_a_runbook_that_exists():
    rules = yaml.safe_load((OPS / "prometheus" / "alerts.yml").read_text())
    for group in rules["groups"]:
        for rule in group["rules"]:
            if "alert" in rule:
                runbook = OPS.parent / rule["annotations"]["runbook"]
                assert runbook.exists(), f"{rule['alert']}: missing {runbook}"
                assert rule["labels"]["severity"] in {"page", "ticket"}
