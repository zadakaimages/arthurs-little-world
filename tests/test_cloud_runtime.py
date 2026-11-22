"""Exercise the cloud process with an isolated save and no model API calls.

Run with: python -m unittest discover -s tests -p 'test_cloud_runtime.py' -v
"""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


class CloudRuntimeTest(unittest.TestCase):
    def test_simulation_health_autosave_and_restart(self):
        with tempfile.TemporaryDirectory(prefix="arthur-cloud-test-") as temporary:
            folder = Path(temporary)
            database = folder / "world.sqlite3"
            log_path = folder / "server.log"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            environment = dict(
                os.environ,
                PORT=str(port),
                ARTHUR_DB=str(database),
                ARTHUR_OWNER_TOKEN="isolated-test-owner-token-1234567890",
                OPENAI_API_KEY="",
                ARTHUR_AI_AUTONOMY="0",
            )
            base_url = f"http://127.0.0.1:{port}"

            def get(path):
                with urlopen(base_url + path, timeout=2) as response:
                    return response.status, json.load(response)

            def start(log):
                process = subprocess.Popen(
                    [sys.executable, "cloud_start.py"],
                    cwd=ROOT,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            self.fail("Cloud process exited: " + log_path.read_text())
                        try:
                            status, _ = get("/healthz")
                            if status == 200:
                                return process
                        except (URLError, TimeoutError, ConnectionError):
                            pass
                        time.sleep(0.1)
                    self.fail("Cloud healthcheck did not become ready: " + log_path.read_text())
                except BaseException:
                    stop(process)
                    raise

            def stop(process):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                        self.fail("Cloud process did not stop cleanly")

            def read_save():
                with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
                    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    row = connection.execute("SELECT value FROM kv WHERE key='state'").fetchone()
                    self.assertIsNotNone(row)
                    return json.loads(row[0])

            def world_minute(state):
                return 1440 * state["day"] + state["minute"]

            with log_path.open("w") as log:
                process = start(log)
                try:
                    _, initial = get("/api/state")
                    # No requests during this interval: the server must keep
                    # simulating even when nobody has the website open.
                    time.sleep(3)
                    _, later = get("/api/state")
                    self.assertGreater(later["seq"], initial["seq"] + 20)
                    self.assertGreater(world_minute(later["state"]), world_minute(initial["state"]) + 2)
                    self.assertGreater(later["state"]["distance"], initial["state"]["distance"])
                    self.assertGreater(world_minute(read_save()), world_minute(initial["state"]))
                    self.assertEqual(get("/healthz")[0], 200)
                finally:
                    stop(process)

                saved = read_save()
                process = start(log)
                try:
                    _, restored = get("/api/state")
                    self.assertNotEqual(restored["run_id"], initial["run_id"])
                    self.assertGreaterEqual(world_minute(restored["state"]), world_minute(saved))
                    self.assertGreaterEqual(restored["state"]["distance"], saved["distance"] - 0.01)
                    self.assertEqual(restored["state"]["day"], saved["day"])
                    self.assertEqual(get("/healthz")[0], 200)
                    time.sleep(0.2)
                    self.assertGreater(get("/api/state")[1]["seq"], restored["seq"])
                finally:
                    stop(process)


if __name__ == "__main__":
    unittest.main()
