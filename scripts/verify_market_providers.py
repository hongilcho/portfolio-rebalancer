"""Compare synthetic quotes and request traces against local pre-refactor Git.

Run from the repository root. Test guards block DB/network IO before app import.
By default this only checks; --write-fixture explicitly recreates the baseline.
"""
import argparse
import importlib.util
import inspect
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
import types


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='64cda1d')
    parser.add_argument('--write-fixture', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-fA-F]{7,40}', args.baseline_ref):
        parser.error('--baseline-ref must be a local commit hash')

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location('provider_isolation', root / 'tests/conftest.py')
    guards = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guards)
    try:
        helpers = runpy.run_path(str(root / 'tests/test_market_provider_refactor.py'))

        def baseline(path):
            source = subprocess.run(['git', 'show', f'{args.baseline_ref}:{path}'],
                                    cwd=root, check=True, capture_output=True,
                                    encoding='utf-8').stdout
            module = types.ModuleType('baseline_' + Path(path).stem)
            exec(compile(source, path, 'exec'), module.__dict__)
            return module

        old = [baseline(path) for path in ('logic/price_fetcher.py',
                                          'logic/crypto_price_fetcher.py',
                                          'logic/dividend_fetcher.py')]
        new = [helpers[name] for name in ('price_fetcher', 'crypto_price_fetcher', 'dividend_fetcher')]
        for before, after in zip(old, new):
            for name, function in vars(before).items():
                if (inspect.isfunction(function) and not name.startswith('_')
                        and function.__module__ == before.__name__):
                    assert str(inspect.signature(function)) == str(
                        inspect.signature(getattr(after, name))), name

        results = {}
        for case in helpers['provider_cases']():
            expected = helpers['run_provider_case'](case, *old)
            actual = helpers['run_provider_case'](case, *new)
            assert expected == actual, f"Provider behavior changed: {case['name']}"
            results[case['name']] = expected

        fixture = helpers['FIXTURE']
        if args.write_fixture:
            fixture.write_text(json.dumps({'baseline_commit': args.baseline_ref, 'results': results},
                                          ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        else:
            recorded = json.loads(fixture.read_text(encoding='utf-8'))
            assert recorded['results'] == results, 'Recorded baseline differs; inspect changes first'
        print(f'{len(results)} synthetic provider scenarios: identical values, '
              'request traces, suffix caches and logs')
    finally:
        guards._isolation.undo()


if __name__ == '__main__':
    main()
