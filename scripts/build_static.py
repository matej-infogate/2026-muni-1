"""Package only reviewed public app/data (never internal documentation); no source import or dependency build."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]
APP_FILES = ('index.html', 'app.mjs', 'model.mjs', 'style.css')
DATA_FILES = ('employees.json', 'courses.json', 'completions.json', 'sessions.json', 'quality.json')


def package(output: Path) -> None:
    """Refuse stale/unknown output rather than silently upload it or delete it."""
    allowed = set(APP_FILES) | {f'data/{n}' for n in DATA_FILES}
    inputs = [(ROOT / 'prototype' / n, output / n) for n in APP_FILES]
    inputs += [(ROOT / 'prototype/data' / n, output / 'data' / n) for n in DATA_FILES]
    for source, target in inputs:
        linked_parent = any(parent.is_symlink() for parent in source.parents if parent == ROOT or ROOT in parent.parents)
        if source.is_symlink() or linked_parent or not source.is_file():
            raise ValueError(f'Missing or linked public input: {source.name}')
    if output.exists():
        for path in output.rglob('*'):
            if path.is_symlink() or (path.is_file() and path.relative_to(output).as_posix() not in allowed):
                raise ValueError('Unapproved build output; inspect it, do not prune automatically')
    for source, target in inputs:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    print(f'Packaged {len(inputs)} public files into {output.name}/')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist-app')
    package(parser.parse_args().output_dir.resolve())
