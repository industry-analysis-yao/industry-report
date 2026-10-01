"""Copy published history into a NEW isolated candidate directory; no model calls."""
import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def prepare(output, source=None):
    source = Path(source or Path(__file__).resolve().parents[1] / 'data').resolve()
    output = Path(output).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError('Candidate workspace must be separate from published data')
    output.mkdir(parents=True, exist_ok=False)
    for path in source.glob('*.json'):
        shutil.copy2(path, output / path.name)
    manifest = dict(status='pending_codex_review', created_at=datetime.now(timezone.utc).isoformat(),
                    source_commit=os.environ.get('GITHUB_SHA', ''),
                    github_run_id=os.environ.get('GITHUB_RUN_ID', ''),
                    api_draft_provider='openrouter/deepseek-chat (optional)',
                    publication_allowed=False)
    (output / 'review_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    prepare(args.output)
