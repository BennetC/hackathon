"""Private append-only round events and an exclusive local submission lock."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import time


STATE_DIR = Path.home() / ".cache" / "fdn-quantco"


class BrokenJournal(ValueError):
    pass


class SubmissionOwnerBusy(ValueError):
    pass


@contextmanager
def submission_owner(directory, *, wait_seconds=0):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(directory / "submission.lock", os.O_CREAT | os.O_RDWR, 0o600)
    until = time.monotonic() + wait_seconds
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                remaining = until - time.monotonic()
                if remaining <= 0:
                    raise SubmissionOwnerBusy("another local tournament runner owns submission") from exc
                time.sleep(min(.5, remaining))
        yield
    finally:
        os.close(fd)


class Journal:
    def __init__(self, directory, clock):
        self.directory, self.clock = directory, clock

    def _path(self, game_id):
        return self.directory / f"game-{game_id}.jsonl"

    def history(self, game_id, *, allow_partial_tail=False):
        path = self._path(game_id)
        if not path.exists():
            return []
        data = path.read_bytes()
        lines = data.split(b"\n")
        if lines[-1] and not allow_partial_tail:
            # A torn record may be evidence of a PUT. Fail closed for this game.
            raise BrokenJournal(f"game {game_id} has an incomplete journal record")
        try:
            return [json.loads(line) for line in lines[:-1]]
        except (ValueError, UnicodeError) as exc:
            raise BrokenJournal(f"game {game_id} has an unreadable journal record") from exc

    def record(self, game_id, state, **details):
        event = {"game_id": game_id, "state": state, "at": self.clock.now().isoformat(), **details}
        line = (json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n").encode()
        path = self._path(game_id)
        created = not path.exists()
        fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "ab") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        if created:
            directory_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return event

    def team_id(self):
        for entry in reversed(self.history(0, allow_partial_tail=True)):
            if entry["state"] == "ACKNOWLEDGED":
                return entry["team_id"]
        return None
