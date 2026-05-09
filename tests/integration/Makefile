# Integration test targets for the Vaultwarden secrets provider.
#
# Usage:
#   make up      # start Vaultwarden container
#   make seed    # populate the running vault with test accounts + items
#   make test    # run the integration test scenarios against the seeded vault
#   make all     # up + seed + test (the typical loop)
#   make logs    # tail container logs
#   make down    # stop the container (preserves vw-data)
#   make clean   # stop AND wipe vw-data + fixtures.json (start over from scratch)
#
# Each target works in this directory; `make all` is the one-shot entry point.

# `uv run --with` ensures the script's deps are isolated and don't pollute any
# active venv. We intentionally do not maintain a requirements.txt here - the
# integration scripts are meant to be runnable from a clean checkout with no
# prior setup beyond `uv` and `docker compose` being on PATH.
#
# `--no-project` is important: without it, uv walks UP from this directory to
# find the repo's root pyproject.toml and creates a uv.lock there, polluting
# the workspace. We don't want any of that - just give us a temp venv with the
# packages I asked for.
UV_RUN := uv run --no-project --with cryptography --with argon2-cffi --with requests python

.PHONY: all up seed test logs down clean status

all: up seed test

up:
	@if [ ! -f .env ]; then cp .env.example .env; fi
	docker compose up -d
	@echo "Waiting for Vaultwarden to become healthy..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -s -o /dev/null -w "%{http_code}" http://localhost:$${VAULTWARDEN_PORT:-18080}/alive | grep -q 200; then \
			echo "Vaultwarden is up."; exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "Vaultwarden didn't respond on /alive within 10s"; exit 1

seed:
	$(UV_RUN) seed_vault.py

test:
	$(UV_RUN) run_integration.py

logs:
	docker compose logs -f vaultwarden

status:
	docker compose ps

down:
	docker compose down

clean:
	docker compose down -v
	@# vw-data is bind-mounted, owned by the container's user. Wipe via a
	@# throwaway alpine container so we don't trip over UID mismatches on the host.
	@if [ -d vw-data ]; then \
		docker run --rm -v "$$(pwd)/vw-data:/data" alpine sh -c 'rm -rf /data/* /data/.??* 2>/dev/null' || true; \
		rmdir vw-data 2>/dev/null || true; \
	fi
	rm -f fixtures.json
	@echo "Stack stopped, vault data and fixtures wiped."
