#!/usr/bin/env python3
"""Read a tmux snapshot and emit live agent and verified-report records."""
import os
import sys
from agent_kinds import KINDS

SEP = '\x1f'


def stat(pid):
    try:
        with open(f'/proc/{pid}/stat', encoding='utf-8') as stream:
            fields = stream.read().rsplit(') ', 1)[1].split()
        return int(fields[1]), fields[19]
    except (OSError, IndexError, ValueError):
        return None


def main():
    owners = {}
    reports = []
    for line in sys.stdin:
        if not line.startswith('P' + SEP):
            continue
        fields = line.rstrip('\n').split(SEP)
        if len(fields) < 24 or fields[8] == '1' or fields[9] == '1':
            continue
        try:
            root = int(fields[16])
        except ValueError:
            continue
        owners[root] = fields[1]
        if fields[17].endswith('-hook') and fields[17][:-5] in KINDS.values():
            reports.append((fields[1], root, fields[17][:-5], fields[22], fields[23]))
    best = {}
    verified = set()
    stat_cache = {}

    def cached_stat(pid):
        if pid not in stat_cache:
            stat_cache[pid] = stat(pid)
        return stat_cache[pid]

    try:
        entries = os.scandir('/proc')
    except OSError:
        return
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                with open(f'{entry.path}/comm', encoding='utf-8') as stream:
                    name = stream.read().strip().removesuffix('.exe')
            except OSError:
                continue
            if name not in KINDS:
                continue
            pid = int(entry.name)
            birth = cached_stat(pid)
            if birth is None:
                continue
            current = pid
            for depth in range(128):
                if current in owners:
                    pane = owners[current]
                    if pane not in best or depth < best[pane][0]:
                        best[pane] = (depth, KINDS[name])
                    for report_pane, report_root, report_kind, report_pid, report_birth in reports:
                        if report_pane == pane and report_root == current and \
                                report_kind == KINDS[name] and report_pid == entry.name and report_birth == birth[1]:
                            verified.add(pane)
                    break
                # Ancestor chains are frequently shared across candidates
                # (siblings under the same shell), so cache stat() lookups
                # instead of reopening /proc/<pid>/stat for the same pid.
                parent = cached_stat(current)
                if parent is None or parent[0] <= 0 or parent[0] == current:
                    break
                current = parent[0]
    for pane, (_, kind) in best.items():
        print(SEP.join(('A', pane, kind)))
    for pane in verified:
        print(SEP.join(('V', pane)))


if __name__ == '__main__':
    main()
