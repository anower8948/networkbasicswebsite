#!/usr/bin/env python3
"""One-command deployment for the Network Learning Platform.

    python3 deploy.py                    # pick a target interactively
    python3 deploy.py docker             # containers on this machine
    python3 deploy.py vps --host root@1.2.3.4
    python3 deploy.py azure --resource-group nlp-prod
    python3 deploy.py --check            # preflight only, deploy nothing

Standard library only, so it runs before anything is installed.

What this can and cannot do, stated plainly:

* **docker** — fully automatic. Builds, starts, migrates, seeds, health-checks,
  and tears the stack back down if it does not come up.
* **vps** — automatic over SSH, provided the one-time setup in
  `docs/DEPLOYMENT.md` has been done (user, database, systemd unit, nginx).
  This script will not create those for you; doing so blind on a machine it
  knows nothing about is how a deploy script breaks a server.
* **azure** — automatic, provided `az login` has been run and the registry and
  resource group exist.
* **cPanel** — *not* automatable. Its Python app is created through a web panel
  with no API. `python3 deploy.py cpanel` prints the checklist and stops.

Nothing here is destructive without asking. Anything that touches a machine
other than this one prompts for confirmation first, unless `--yes` is passed.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

COMPOSE_URL = "http://localhost:8080"
HEALTH_PATH = "/api/v1/health"

# Values the production boot guard rejects. Checked here too so a bad env file
# is caught before anything is built, rather than by a container that will not
# start. The application remains the authority; see `app/core/config.py`.
PLACEHOLDERS = {"", "CHANGE_ME", "changeme", "REPLACE_ME"}


# --------------------------------------------------------------------------- #
# Console
# --------------------------------------------------------------------------- #
class Console:
    """Terminal output. Colour only when a terminal is actually attached."""

    def __init__(self) -> None:
        self.colour = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
        self._step = 0

    def _paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.colour else text

    def step(self, message: str) -> None:
        self._step += 1
        print(f"\n{self._paint('1;34', f'[{self._step}]')} {self._paint('1', message)}")

    def info(self, message: str) -> None:
        print(f"    {message}")

    def ok(self, message: str) -> None:
        print(f"    {self._paint('32', '✓')} {message}")

    def warn(self, message: str) -> None:
        print(f"    {self._paint('33', '!')} {message}")

    def fail(self, message: str) -> None:
        print(f"    {self._paint('31', '✗')} {message}", file=sys.stderr)

    def banner(self, message: str) -> None:
        line = "─" * min(len(message) + 4, 76)
        print(f"\n{self._paint('1;36', line)}")
        print(f"{self._paint('1;36', '  ' + message)}")
        print(f"{self._paint('1;36', line)}")


console = Console()


class DeployError(RuntimeError):
    """A failure with a message already fit for a human to read."""


# --------------------------------------------------------------------------- #
# Process helpers
# --------------------------------------------------------------------------- #
@dataclass
class Options:
    target: str = "docker"
    host: str | None = None
    resource_group: str | None = None
    registry: str | None = None
    environment: str = "prod"
    skip_tests: bool = False
    skip_seed: bool = False
    dry_run: bool = False
    assume_yes: bool = False
    keep_on_failure: bool = False


def run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
    check: bool = True,
    env: dict[str, str] | None = None,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command, echoing it so the log shows exactly what happened."""
    printable = " ".join(command)
    if dry_run:
        console.info(f"[dry run] {printable}")
        return subprocess.CompletedProcess(command, 0, "", "")

    console.info(f"$ {printable}")
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=capture,
        env={**os.environ, **(env or {})},
        check=False,
    )
    if check and result.returncode != 0:
        if capture and result.stderr:
            console.fail(result.stderr.strip()[:2000])
        raise DeployError(f"Command failed ({result.returncode}): {printable}")
    return result


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


def confirm(question: str, *, assume_yes: bool) -> bool:
    """Ask before doing anything to a machine other than this one."""
    if assume_yes:
        console.info(f"{question} — assuming yes (--yes)")
        return True
    if not sys.stdin.isatty():
        raise DeployError(
            f"{question} Needs confirmation, but there is no terminal. Pass --yes."
        )
    reply = input(f"    {question} [y/N] ").strip().lower()
    return reply in {"y", "yes"}


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
def wait_for_health(url: str, *, attempts: int = 40, delay: float = 3.0) -> bool:
    """Poll until the API answers, or give up.

    Deliberately generous: a cold container has to install nothing but does
    have to run migrations, and a first PostgreSQL start is slower than a
    warm one.
    """
    console.info(f"Waiting for {url} …")
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    payload = json.loads(response.read().decode())
                    console.ok(
                        f"Healthy after {attempt} attempt(s) "
                        f"— {payload.get('environment', '?')} / {payload.get('version', '?')}"
                    )
                    return True
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
            pass
        time.sleep(delay)
    console.fail(f"No healthy response after {attempts} attempts.")
    return False


# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #
def check_layout() -> None:
    if (
        not (BACKEND / "app" / "main.py").exists()
        or not (FRONTEND / "package.json").exists()
    ):
        raise DeployError(
            f"{ROOT} does not look like the project root — expected backend/ and frontend/."
        )


def check_tools(required: Sequence[str]) -> None:
    missing = [tool for tool in required if not have(tool)]
    if missing:
        raise DeployError(f"Missing required tool(s): {', '.join(missing)}")
    for tool in required:
        console.ok(f"{tool} found")


def backend_python() -> list[str]:
    """The interpreter that has the backend's dependencies, if there is one."""
    venv = BACKEND / ".venv" / "bin" / "python"
    return [str(venv)] if venv.exists() else [sys.executable]


def run_tests(options: Options) -> None:
    """Run the suites before deploying anything.

    A deploy script that ships a red build is worse than no deploy script: it
    makes the broken state look sanctioned.
    """
    if options.skip_tests:
        console.warn("Tests skipped (--skip-tests). You are shipping unverified code.")
        return

    python = backend_python()
    if (BACKEND / ".venv").exists():
        run([*python, "-m", "pytest", "-q"], cwd=BACKEND, dry_run=options.dry_run)
        console.ok("Backend suite passed")
    else:
        console.warn("No backend/.venv — skipping the backend suite.")

    if have("npm") and (FRONTEND / "node_modules").exists():
        run(["npm", "test", "--", "--run"], cwd=FRONTEND, dry_run=options.dry_run)
        console.ok("Frontend suite passed")
    else:
        console.warn("No frontend/node_modules — skipping the frontend suite.")


# --------------------------------------------------------------------------- #
# Environment file
# --------------------------------------------------------------------------- #
def generate_secret() -> str:
    return secrets.token_urlsafe(64)


def ensure_env_file(options: Options) -> Path:
    """Create `.env` from the example on first run, with a real secret key.

    An existing file is never rewritten. Regenerating `SECRET_KEY` would sign
    out every user on the platform, and a deploy script is the last place that
    should happen by surprise.
    """
    env_path = ROOT / ".env"
    if env_path.exists():
        console.ok(f"{env_path.name} exists (left untouched)")
        # A blank key is not a configured key. The app falls back to generating
        # one, which works — but a *fresh* key per restart signs every session
        # out on every restart, and that is worth saying out loud.
        if not read_env(env_path).get("SECRET_KEY", "").strip():
            console.warn(
                f"{env_path.name} has no SECRET_KEY. A new one is generated on every "
                "restart, so everyone is signed out each time the API restarts."
            )
            console.info(
                "Fix: SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')"
            )
        return env_path

    example = BACKEND / ".env.example"
    console.info(f"Creating {env_path.name}")
    if options.dry_run:
        return env_path

    body = example.read_text() if example.exists() else ""
    lines: list[str] = []
    seen_secret = False
    for line in body.splitlines():
        if line.startswith("SECRET_KEY="):
            lines.append(f"SECRET_KEY={generate_secret()}")
            seen_secret = True
        else:
            lines.append(line)
    if not seen_secret:
        lines.append(f"SECRET_KEY={generate_secret()}")

    env_path.write_text("\n".join(lines) + "\n")
    env_path.chmod(0o600)
    console.ok(f"{env_path.name} created with a generated SECRET_KEY (mode 600)")
    return env_path


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def check_production_env(path: Path) -> None:
    """Catch a half-filled env file before building anything.

    Mirrors the application's own boot guard. That guard is still the
    authority — this just moves the failure from "the container will not
    start" to "the deploy stopped before it built anything".
    """
    values = read_env(path)
    if values.get("ENVIRONMENT") != "production":
        return

    problems: list[str] = []
    for key in ("SECRET_KEY", "DATABASE_URL", "FRONTEND_URL", "CORS_ORIGINS"):
        if values.get(key, "") in PLACEHOLDERS or "CHANGE_ME" in values.get(key, ""):
            problems.append(f"{key} is unset or still a placeholder")
    if len(values.get("SECRET_KEY", "")) < 32:
        problems.append("SECRET_KEY is shorter than 32 characters")
    if values.get("DATABASE_URL", "").startswith("sqlite"):
        problems.append("DATABASE_URL points at SQLite; production needs PostgreSQL")
    if not values.get("FRONTEND_URL", "").startswith("https://"):
        problems.append("FRONTEND_URL must be https")
    if values.get("EMAIL_BACKEND") == "console":
        problems.append("EMAIL_BACKEND=console would send password resets to the log")

    if problems:
        raise DeployError(
            "This .env is not ready for production:\n      - "
            + "\n      - ".join(problems)
        )
    console.ok("Production environment file looks complete")


# --------------------------------------------------------------------------- #
# Targets
# --------------------------------------------------------------------------- #
@dataclass
class Target:
    name: str
    description: str
    tools: list[str] = field(default_factory=list)

    def preflight(self, options: Options) -> None:
        """Target-specific readiness, beyond "the binary is on PATH"."""

    def deploy(self, options: Options) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class DockerTarget(Target):
    """Containers on this machine — the fully automatic path."""

    def __init__(self) -> None:
        super().__init__(
            name="docker",
            description="Docker Compose on this machine (PostgreSQL + API + nginx)",
            tools=["docker"],
        )

    def preflight(self, options: Options) -> None:
        """Check the daemon answers, not just that the CLI is installed.

        `docker` on PATH with nothing behind it is the single most common way
        this fails, and the raw daemon error ("dial unix … no such file or
        directory") tells a user nothing about what to do next.
        """
        if options.dry_run:
            return
        probe = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            raise DeployError(
                "Docker is installed but the daemon is not responding.\n"
                "      Start Docker Desktop (or OrbStack, or `sudo systemctl start docker`)\n"
                "      and run this again."
            )
        console.ok(f"Docker daemon responding (engine {probe.stdout.strip()})")

    def deploy(self, options: Options) -> None:
        compose = self._compose_command()

        console.step("Preparing configuration")
        env_path = ensure_env_file(options)
        check_production_env(env_path)

        console.step("Building images")
        run([*compose, "build"], cwd=ROOT, dry_run=options.dry_run)

        console.step("Starting the stack")
        # `--remove-orphans` keeps a renamed service from lingering across
        # deploys and quietly holding a port.
        run(
            [*compose, "up", "-d", "--remove-orphans"],
            cwd=ROOT,
            dry_run=options.dry_run,
        )

        console.step("Waiting for the API")
        if options.dry_run:
            console.info("[dry run] would poll the health endpoint")
        elif not wait_for_health(f"{COMPOSE_URL}{HEALTH_PATH}"):
            self._on_failure(compose, options)
            raise DeployError("The stack did not become healthy.")

        if not options.skip_seed:
            console.step("Seeding the catalogue")
            # Idempotent: upserts by slug and never touches learner progress,
            # so running it on every deploy is safe.
            run(
                [*compose, "exec", "-T", "api", "python", "-m", "app.seeds"],
                cwd=ROOT,
                dry_run=options.dry_run,
            )

        console.step("Verifying")
        if not options.dry_run:
            self._verify()

        console.banner(f"Deployed — open {COMPOSE_URL}")
        console.info("The first account you register becomes the administrator.")
        console.info(f"Logs:  {' '.join(compose)} logs -f api")
        console.info(f"Stop:  {' '.join(compose)} down")

    @staticmethod
    def _compose_command() -> list[str]:
        """`docker compose` on modern Docker, `docker-compose` on older."""
        probe = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            return ["docker", "compose"]
        if have("docker-compose"):
            return ["docker-compose"]
        raise DeployError("Neither `docker compose` nor `docker-compose` is available.")

    @staticmethod
    def _verify() -> None:
        """Confirm the things that are easy to get silently wrong."""
        try:
            request = urllib.request.Request(COMPOSE_URL, method="GET")
            with urllib.request.urlopen(request, timeout=10) as response:
                headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            console.warn(f"Could not fetch the web tier: {error}")
            return

        if "content-security-policy" in headers:
            console.ok("Security headers are being served")
        else:
            console.warn(
                "No Content-Security-Policy on the web tier — check nginx.conf"
            )

    def _on_failure(self, compose: list[str], options: Options) -> None:
        console.fail("Recent API logs:")
        run([*compose, "logs", "--tail", "40", "api"], cwd=ROOT, check=False)
        if options.keep_on_failure:
            console.warn(
                "Leaving the stack up (--keep-on-failure) so you can inspect it."
            )
            return
        console.info("Stopping the stack.")
        run([*compose, "down"], cwd=ROOT, check=False)


class VpsTarget(Target):
    """A Linux host over SSH, using the release script in infra/vps/."""

    def __init__(self) -> None:
        super().__init__(
            name="vps",
            description="Linux VPS over SSH (systemd + nginx)",
            tools=["ssh", "rsync"],
        )

    def deploy(self, options: Options) -> None:
        if not options.host:
            raise DeployError(
                "The vps target needs --host, e.g. --host root@203.0.113.10"
            )
        host = options.host

        console.step(f"Checking {host}")
        if not options.dry_run:
            probe = run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, "true"],
                capture=True,
                check=False,
            )
            if probe.returncode != 0:
                raise DeployError(
                    f"Cannot reach {host} over SSH with key authentication. "
                    "Check the host, and that your key is authorised."
                )
        console.ok("SSH reachable")

        remote_setup = run(
            [
                "ssh",
                host,
                "test -f /etc/nlp/api.env && test -f /etc/systemd/system/nlp-api.service",
            ],
            check=False,
            dry_run=options.dry_run,
        )
        if not options.dry_run and remote_setup.returncode != 0:
            raise DeployError(
                "This host has not had its one-time setup.\n"
                "      Follow the 'Linux VPS' section of docs/DEPLOYMENT.md first —\n"
                "      creating the user, database, systemd unit and nginx site blind\n"
                "      is how a deploy script breaks a server."
            )
        console.ok("Host is prepared")

        if not confirm(f"Deploy to {host}?", assume_yes=options.assume_yes):
            raise DeployError("Cancelled.")

        console.step("Copying the release")
        # Exclusions matter: node_modules and .venv are host-specific and would
        # dominate the transfer.
        run(
            [
                "rsync",
                "-az",
                "--delete",
                "--exclude",
                ".git",
                "--exclude",
                "node_modules",
                "--exclude",
                ".venv",
                "--exclude",
                "dist",
                "--exclude",
                "__pycache__",
                "--exclude",
                "*.db",
                f"{ROOT}/",
                f"{host}:/tmp/nlp-release/",
            ],
            dry_run=options.dry_run,
        )

        console.step("Running the remote deploy")
        # infra/vps/deploy.sh builds, migrates, swaps symlinks, restarts, and
        # rolls itself back if the health check fails.
        run(
            [
                "ssh",
                host,
                "sudo bash /tmp/nlp-release/infra/vps/deploy.sh /tmp/nlp-release",
            ],
            dry_run=options.dry_run,
        )

        console.banner(f"Deployed to {host}")
        console.info(f"Logs:  ssh {host} journalctl -u nlp-api -f")


class AzureTarget(Target):
    """Azure App Service via the Bicep template in infra/azure/."""

    def __init__(self) -> None:
        super().__init__(
            name="azure",
            description="Azure App Service (Bicep, container images)",
            tools=["az", "docker"],
        )

    def deploy(self, options: Options) -> None:
        group = options.resource_group
        registry = options.registry
        if not group:
            raise DeployError("The azure target needs --resource-group")
        if not registry:
            raise DeployError("The azure target needs --registry (the ACR name)")

        console.step("Checking the Azure session")
        account = run(
            ["az", "account", "show", "-o", "json"], capture=True, check=False
        )
        if account.returncode != 0:
            raise DeployError("Not signed in to Azure. Run `az login` first.")
        if not options.dry_run:
            subscription = json.loads(account.stdout)
            console.ok(f"Subscription: {subscription.get('name')}")

        tag = self._image_tag()
        console.ok(f"Image tag: {tag}")

        if not confirm(
            f"Deploy tag {tag} to resource group {group}?",
            assume_yes=options.assume_yes,
        ):
            raise DeployError("Cancelled.")

        console.step("Building and pushing images")
        run(["az", "acr", "login", "--name", registry], dry_run=options.dry_run)
        for image, context in (("nlp-api", BACKEND), ("nlp-web", FRONTEND)):
            reference = f"{registry}.azurecr.io/{image}:{tag}"
            run(
                ["docker", "build", "-t", reference, str(context)],
                dry_run=options.dry_run,
            )
            run(["docker", "push", reference], dry_run=options.dry_run)

        console.step("Deploying infrastructure")
        run(
            [
                "az",
                "deployment",
                "group",
                "create",
                "--resource-group",
                group,
                "--template-file",
                str(ROOT / "infra" / "azure" / "main.bicep"),
                "--parameters",
                str(ROOT / "infra" / "azure" / "main.parameters.json"),
                "--parameters",
                f"imageTag={tag}",
                f"environmentName={options.environment}",
            ],
            dry_run=options.dry_run,
        )

        console.step("Waiting for the API")
        url = f"https://nlp-{options.environment}-api.azurewebsites.net{HEALTH_PATH}"
        if options.dry_run:
            console.info(f"[dry run] would poll {url}")
        elif not wait_for_health(url, attempts=40, delay=10):
            raise DeployError(
                "The deployment did not become healthy.\n"
                f"      Roll back:  az webapp config container set --name nlp-{options.environment}-api "
                f"--resource-group {group} --docker-custom-image-name "
                f"{registry}.azurecr.io/nlp-api:<previous-tag>"
            )

        console.banner("Deployed to Azure")
        console.info(
            "Migrations: run `alembic upgrade head` as a one-shot job — see DEPLOYMENT.md."
        )

    @staticmethod
    def _image_tag() -> str:
        """The commit SHA, never `latest`.

        A mutable tag makes "which build is running?" unanswerable during an
        incident and turns a rollback into a rebuild.
        """
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        console.warn(
            f"Not a git repository — tagging with a timestamp ({stamp}) instead."
        )
        return stamp


class CpanelTarget(Target):
    """Not automatable. Prints the checklist and stops."""

    def __init__(self) -> None:
        super().__init__(
            name="cpanel",
            description="cPanel shared hosting (manual — prints a checklist)",
        )

    def deploy(self, options: Options) -> None:
        console.step("Building the frontend bundle")
        if have("npm"):
            run(["npm", "ci"], cwd=FRONTEND, dry_run=options.dry_run)
            run(["npm", "run", "build"], cwd=FRONTEND, dry_run=options.dry_run)
            console.ok(f"Bundle ready at {FRONTEND / 'dist'}")
        else:
            console.warn(
                "npm not found — build the frontend elsewhere and upload dist/."
            )

        console.banner("cPanel deployment cannot be automated")
        print(
            """
    cPanel creates its Python application through a web panel with no API, so
    the remaining steps are yours. In order:

      1. cPanel → Setup Python App
           Python 3.12 · application root `nlp` · application URL `/api`
           startup file `passenger_wsgi.py`
      2. Upload  backend/                      → the application root
         Upload  infra/cpanel/passenger_wsgi.py → beside it
      3. In the virtualenv cPanel prints:
           pip install -e ./backend
           pip install a2wsgi
      4. Add every variable from infra/vps/api.env.example in the app's
         Environment Variables panel.
      5. From the cPanel terminal:
           alembic upgrade head
           python -m app.seeds
      6. Upload  frontend/dist/*               → public_html
         Upload  infra/cpanel/.htaccess        → public_html
      7. Restart the app from the cPanel panel.

    Worth knowing before you commit to this target: cPanel runs the app through
    a WSGI bridge, so every request occupies a worker for its whole duration
    and the async database driver's advantage is lost. It works correctly, but
    expect several times less throughput than the other targets.
            """.rstrip()
        )


TARGETS: dict[str, Target] = {
    target.name: target
    for target in (DockerTarget(), VpsTarget(), AzureTarget(), CpanelTarget())
}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def choose_target() -> str:
    console.banner("Network Learning Platform — deploy")
    print("\n    Where should this go?\n")
    names = list(TARGETS)
    for index, name in enumerate(names, start=1):
        print(f"      {index}. {name:<8} {TARGETS[name].description}")
    print()

    while True:
        reply = input("    Choose 1-4 (or q to quit): ").strip().lower()
        if reply in {"q", "quit", ""}:
            raise DeployError("Cancelled.")
        if reply.isdigit() and 1 <= int(reply) <= len(names):
            return names[int(reply) - 1]
        if reply in TARGETS:
            return reply
        console.warn("Not a valid choice.")


def preflight(options: Options, target: Target) -> None:
    console.step("Preflight")
    check_layout()
    console.ok(f"Project root: {ROOT}")
    check_tools(target.tools)
    # Before the suites, not after: finding out the daemon is down should not
    # cost two minutes of testing first.
    target.preflight(options)
    run_tests(options)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deploy.py",
        description="Deploy the Network Learning Platform.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 deploy.py                          pick a target interactively\n"
            "  python3 deploy.py docker                   containers on this machine\n"
            "  python3 deploy.py docker --skip-tests      skip the suites (not advised)\n"
            "  python3 deploy.py vps --host root@1.2.3.4\n"
            "  python3 deploy.py azure --resource-group nlp-prod --registry nlpregistry\n"
            "  python3 deploy.py --check                  preflight only\n"
        ),
    )
    parser.add_argument(
        "target",
        nargs="?",
        choices=sorted(TARGETS),
        help="where to deploy (asks if omitted)",
    )
    parser.add_argument(
        "--host", help="SSH target for the vps deployment, e.g. root@203.0.113.10"
    )
    parser.add_argument("--resource-group", help="Azure resource group")
    parser.add_argument("--registry", help="Azure container registry name")
    parser.add_argument(
        "--environment",
        default="prod",
        choices=["dev", "staging", "prod"],
        help="Azure environment",
    )
    parser.add_argument(
        "--skip-tests", action="store_true", help="do not run the test suites"
    )
    parser.add_argument(
        "--skip-seed", action="store_true", help="do not seed the catalogue"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print commands, change nothing"
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="do not prompt for confirmation"
    )
    parser.add_argument(
        "--keep-on-failure",
        action="store_true",
        help="leave a failed docker stack running so it can be inspected",
    )
    parser.add_argument(
        "--check", action="store_true", help="run preflight only, deploy nothing"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        target_name = args.target or ("docker" if args.check else choose_target())
        target = TARGETS[target_name]

        options = Options(
            target=target_name,
            host=args.host,
            resource_group=args.resource_group,
            registry=args.registry,
            environment=args.environment,
            skip_tests=args.skip_tests,
            skip_seed=args.skip_seed,
            dry_run=args.dry_run,
            assume_yes=args.yes,
            keep_on_failure=args.keep_on_failure,
        )

        console.banner(f"Target: {target.name} — {target.description}")
        if options.dry_run:
            console.warn("Dry run: commands are printed, nothing is executed.")

        preflight(options, target)

        if args.check:
            console.banner("Preflight passed — nothing deployed (--check)")
            return 0

        target.deploy(options)
        return 0

    except DeployError as error:
        console.fail(str(error))
        return 1
    except KeyboardInterrupt:
        console.fail("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
