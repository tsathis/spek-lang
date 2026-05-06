from spek.effects.python import check
from spek.parser import parse


def spec_of(source: str):
    spec_file, diags = parse(source, "t.spek")
    assert not [d for d in diags if d.is_error], [d.render() for d in diags]
    return spec_file.specs[0]


def run(spec_source: str, impl: str):
    diags, observations = check(spec_of(spec_source), impl, "impl.py")
    return [d.code for d in diags], {(o.tag, o.symbol) for o in observations}


NET_SPEC = "fetch(id) -> user | missing\n  !net\n  1 ok\n  2 missing\n"


def test_declared_effect_matches():
    codes, seen = run(NET_SPEC, "import requests\n\ndef fetch(id):\n    return requests.get(id)\n")
    assert codes == []
    assert ("net", "requests.get") in seen


def test_undeclared_effect_is_an_error():
    codes, _ = run(
        "fetch(id) -> user | missing\n  !fs\n  1 ok\n  2 missing\n",
        "import requests\nimport shutil\n\n"
        "def fetch(id):\n    shutil.copy('a', 'b')\n    return requests.get(id)\n",
    )
    assert codes == ["E101"]


def test_effects_of_module_local_helpers_count():
    codes, seen = run(
        NET_SPEC,
        "import requests\n\n"
        "def _log(x):\n    with open('/tmp/l', 'a') as f:\n        f.write(x)\n\n"
        "def fetch(id):\n    _log(id)\n    return requests.get(id)\n",
    )
    assert codes == ["E101"]
    assert ("fs", "open") in seen


def test_unrelated_functions_do_not_count():
    codes, _ = run(
        NET_SPEC,
        "import requests\nimport shutil\n\n"
        "def fetch(id):\n    return requests.get(id)\n\n"
        "def elsewhere():\n    shutil.rmtree('/')\n",
    )
    assert codes == []


def test_declared_effect_the_code_never_does_is_drift():
    codes, _ = run(
        "login(e, p) -> ok | wrong\n  !hash\n  (1, 2) ok\n  (1, 3) wrong\n",
        "def login(e, p):\n    if p != 'secret':\n        raise WrongError()\n    return e\n",
    )
    assert codes == ["E103"]


def test_drift_softens_to_a_warning_behind_an_opaque_call():
    codes, _ = run(
        "login(e, p) -> ok | wrong\n  !hash\n  (1, 2) ok\n  (1, 3) wrong\n",
        "from mycrypto import verify\n\n"
        "def login(e, p):\n    if not verify(p):\n        raise WrongError()\n    return e\n",
    )
    assert codes == ["W301"]


def test_pure_stdlib_calls_do_not_soften_drift():
    codes, _ = run(
        "f(x) -> ok | no\n  !hash\n  1 ok\n  2 no\n",
        "import json\n\ndef f(x):\n    return json.dumps(x)\n",
    )
    assert codes == ["E103"]


def test_import_aliases_resolve():
    codes, seen = run(
        NET_SPEC, "import requests as rq\n\ndef fetch(id):\n    return rq.get(id)\n"
    )
    assert codes == [] and ("net", "requests.get") in seen


def test_from_import_resolves():
    codes, seen = run(
        "digest(x) -> text\n  !hash\n  1 ok\n",
        "from hashlib import sha256\n\ndef digest(x):\n    return sha256(x).hexdigest()\n",
    )
    assert codes == [] and ("hash", "hashlib.sha256") in seen


def test_pure_path_helpers_are_not_filesystem_access():
    codes, _ = run(
        "join(a, b) -> text\n  (1, 2) ok\n",
        "import os\n\ndef join(a, b):\n    return os.path.join(a, b)\n",
    )
    assert codes == []


def test_module_level_mutable_state_is_a_heuristic_warning():
    codes, seen = run(
        "get(key) -> value | miss\n  1 ok\n  2 miss\n",
        "_STORE = {}\n\ndef get(key):\n    return _STORE[key]\n",
    )
    assert codes == ["W308"]
    assert ("mem", "_STORE") in seen


def test_declared_mem_is_satisfied_by_instance_state():
    codes, _ = run(
        "cache.get(key) -> value | miss\n  !mem\n  1 ok\n  2 miss\n",
        "class Cache:\n    def __init__(self):\n        self._d = {}\n\n"
        "    def get(self, key):\n        return self._d[key]\n",
    )
    assert codes == []


def test_lru_cache_counts_as_kept_state():
    codes, seen = run(
        "f(x) -> y\n  !mem\n  1 ok\n",
        "import functools\n\n@functools.lru_cache\ndef f(x):\n    return x\n",
    )
    assert codes == [] and ("mem", "functools.lru_cache") in seen


def test_missing_target_function():
    codes, _ = run(NET_SPEC, "import requests\n\ndef other():\n    return requests.get(1)\n")
    assert codes == ["E204"]


def test_method_is_found_for_a_dotted_spec_name():
    codes, _ = run(
        "cache.get(key) -> value | miss\n  !mem\n  1 ok\n  2 miss\n",
        "class Cache:\n    def get(self, key):\n        return self._d[key]\n",
    )
    assert codes == []


def test_implementation_that_does_not_parse():
    codes, _ = run(NET_SPEC, "def fetch(:\n")
    assert codes == ["E207"]


def test_recursive_helpers_terminate():
    codes, _ = run(
        NET_SPEC,
        "import requests\n\n"
        "def a(x):\n    return b(x)\n\n"
        "def b(x):\n    return a(x)\n\n"
        "def fetch(id):\n    a(id)\n    return requests.get(id)\n",
    )
    assert codes == []
