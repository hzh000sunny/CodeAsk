"""Runtime environment guardrails for third-party libraries."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_codeask_import_defaults_litellm_to_local_model_cost_map() -> None:
    env = os.environ.copy()
    env["LITELLM_LOCAL_MODEL_COST_MAP"] = "False"
    env["PYTHONPATH"] = f"{ROOT / 'src'}:{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "import codeask; "
                "print(os.environ.get('LITELLM_LOCAL_MODEL_COST_MAP'))"
            ),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "True"


def test_codeask_llm_client_forces_litellm_local_model_cost_map() -> None:
    env = os.environ.copy()
    env.pop("LITELLM_LOCAL_MODEL_COST_MAP", None)
    env["PYTHONPATH"] = f"{ROOT / 'src'}:{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "import codeask.llm.client; "
                "from litellm.litellm_core_utils.get_model_cost_map "
                "import get_model_cost_map_source_info; "
                "print(json.dumps(get_model_cost_map_source_info(), sort_keys=True))"
            ),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "fallback_reason": None,
        "is_env_forced": True,
        "source": "local",
        "url": None,
    }
